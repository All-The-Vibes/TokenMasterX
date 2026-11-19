"""Pillar 5 repository & cross-session recall brief (`repo_brief.py`, `brainspace_sessionstart.py`, host wiring, and `/tokenomics` accounting)."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import pytest

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

from brainspace import repo_brief, symbol_index, tokens  # noqa: E402
from hosts import (  # noqa: E402
    copilot_hook_status,
    copilot_session_hook_status,
    wire_copilot_hook,
    wire_copilot_session_hook,
)


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SKILL / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


sessionstart_mod = _load("brainspace_sessionstart_test", "brainspace_sessionstart.py")
setup_mod = _load("setup_repo_brief_test", "setup.py")
brainspace_setup_mod = _load("brainspace_setup_brief_test", "brainspace_setup.py")
tokenomics_mod = _load("tokenomics_brief_test", "tokenomics.py")
bridge_mod = _load("bridge_brief_test", "brainspace_copilot_bridge.py")


def _make_sample_repo(root: Path) -> Path:
    """Create a multi-module sample repo with core hubs, string `.join` noise, examples, and tests."""
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "src" / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "examples").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)

    (root / "src" / "pkg" / "core.py").write_text(
        "def dispatch_event(name: str, payload: dict) -> str:\n"
        "    \"\"\"Central event router called across modules.\"\"\"\n"
        "    parts = [name, str(len(payload))]\n"
        "    return ':'.join(parts)\n\n"
        "class Engine:\n"
        "    def execute(self, job: str) -> str:\n"
        "        return dispatch_event('run', {'job': job})\n\n"
        "class Trap:\n"
        "    def join(self, items: list[str]) -> str:\n"
        "        \"\"\"Must NOT absorb unrelated str.join calls across the codebase.\"\"\"\n"
        "        return '|'.join(items)\n",
        encoding="utf-8",
    )
    (root / "src" / "pkg" / "api.py").write_text(
        "from pkg import core\n\n"
        "def handle_request(body: dict) -> str:\n"
        "    tag = ','.join(sorted(body.keys()))\n"
        "    eng = core.Engine()\n"
        "    res = eng.execute(tag)\n"
        "    return core.dispatch_event('api', {'res': res})\n",
        encoding="utf-8",
    )
    (root / "src" / "pkg" / "worker.py").write_text(
        "from pkg import core\n\n"
        "def process_batch(batch: list[str]) -> list[str]:\n"
        "    merged = ';'.join(batch)\n"
        "    return [core.dispatch_event('batch', {'merged': merged})]\n",
        encoding="utf-8",
    )
    (root / "src" / "pkg" / "cli.py").write_text(
        "from pkg import api, core\n\n"
        "def main(argv: list[str] | None = None) -> int:\n"
        "    raw = ' '.join(argv or [])\n"
        "    out = api.handle_request({'argv': raw})\n"
        "    core.dispatch_event('cli', {'out': out})\n"
        "    return 0\n",
        encoding="utf-8",
    )
    (root / "examples" / "demo.py").write_text(
        "def main() -> int:\n"
        "    items = ['a', 'b', 'c']\n"
        "    print('-'.join(items))\n"
        "    return 0\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_core.py").write_text(
        "from pkg import core\n\n"
        "def test_dispatch():\n"
        "    assert core.dispatch_event('x', {}) == 'x:0'\n",
        encoding="utf-8",
    )
    return root


def test_build_brief_deterministic_bounded_and_valid_read_symbol_targets(tmp_path):
    repo = _make_sample_repo(tmp_path / "repo")
    idx = symbol_index.SymbolIndex(repo)
    try:
        text1, meta1 = repo_brief.build_brief(repo, index=idx, budget=repo_brief.BRIEF_BUDGET)
        text2, meta2 = repo_brief.build_brief(repo, index=idx, budget=repo_brief.BRIEF_BUDGET)
        assert text1 == text2
        assert meta1["sha256"] == meta2["sha256"]
        assert 0 < meta1["tokens"] <= repo_brief.BRIEF_BUDGET
        assert meta1["estimated_tokens"] <= repo_brief.BRIEF_BUDGET
        assert tokens.count_tokens(text1) <= repo_brief.BRIEF_BUDGET
        assert symbol_index._count(text1) <= repo_brief.BRIEF_BUDGET

        # Core hub surfaces; Trap.join is NOT falsely promoted by `','.join(...)` calls; examples/demo.py is skipped.
        assert "src/pkg/core.py::dispatch_event" in text1
        assert "Trap.join" not in text1
        assert "examples/demo.py" not in text1
        assert "tests/test_core.py" not in text1

        # Every emitted `path::Symbol` target resolves cleanly via `SymbolIndex.read(target)`.
        targets = re.findall(r"(?:Hub|Entry|Recall): (\S+::\S+)", text1)
        assert targets
        for target in targets:
            out = idx.read(target)
            assert not out.startswith("Error:"), f"{target} failed SymbolIndex.read: {out}"
    finally:
        idx.close()


@pytest.mark.parametrize("tight_budget", [80, 120, 180, 320])
def test_build_brief_respects_arbitrary_tight_budgets_under_exact_and_fallback_counters(
    tmp_path, monkeypatch, tight_budget
):
    repo = _make_sample_repo(tmp_path / "repo")
    idx = symbol_index.SymbolIndex(repo)
    try:
        text, meta = repo_brief.build_brief(repo, index=idx, budget=tight_budget)
        assert tokens.count_tokens(text) <= tight_budget
        assert symbol_index._count(text) <= tight_budget
        assert meta["tokens"] <= tight_budget

        # Force heuristic estimator fallback (`_encoder() -> None`).
        monkeypatch.setattr(tokens, "_encoder", lambda: None)
        text_fb, meta_fb = repo_brief.build_brief(repo, index=idx, budget=tight_budget)
        assert tokens.estimate(text_fb) <= tight_budget
        assert symbol_index._count(text_fb) <= tight_budget
        assert meta_fb["estimated_tokens"] <= tight_budget
    finally:
        idx.close()


def test_frozen_epoch_recall_recording_and_self_healing_refresh(tmp_path):
    repo = _make_sample_repo(tmp_path / "repo")
    meta_cold = repo_brief.write_brief(repo, include_recall=True)
    brief_path = repo / ".token-master" / "brief.md"
    cold_bytes = brief_path.read_bytes()
    assert meta_cold["recall_count"] == 0

    idx = symbol_index.SymbolIndex(repo)
    try:
        for _ in range(3):
            out = symbol_index.dispatch(idx, "read_symbol", {"target": "src/pkg/worker.py::process_batch"})
            repo_brief.record_recall(idx, "read_symbol", {"target": "src/pkg/worker.py::process_batch"}, out)
        # Error lookups and test lookups are ignored.
        err = symbol_index.dispatch(idx, "read_symbol", {"target": "src/pkg/worker.py::missing_fn"})
        repo_brief.record_recall(idx, "read_symbol", {"target": "src/pkg/worker.py::missing_fn"}, err)
        test_out = symbol_index.dispatch(idx, "read_symbol", {"target": "tests/test_core.py::test_dispatch"})
        repo_brief.record_recall(idx, "read_symbol", {"target": "tests/test_core.py::test_dispatch"}, test_out)
    finally:
        idx.close()

    # Frozen-epoch invariant: active navigation never mutates `.token-master/brief.md` mid-session!
    assert brief_path.read_bytes() == cold_bytes
    assert (repo / ".token-master" / "recall.jsonl").is_file()

    # Shift line numbers in worker.py and add a second recalled symbol that we later delete.
    (repo / "src" / "pkg" / "worker.py").write_text(
        "# header line 1\n# header line 2\n# header line 3\n"
        "from pkg import core\n\n"
        "def process_batch(batch: list[str]) -> list[str]:\n"
        "    merged = ';'.join(batch)\n"
        "    return [core.dispatch_event('batch', {'merged': merged})]\n",
        encoding="utf-8",
    )
    with (repo / ".token-master" / "recall.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"tool": "read_symbol", "path": "src/pkg/worker.py", "qualname": "deleted_helper"}) + "\n")

    # Run `setup.py REPO --refresh-brief` via subprocess to test the real CLI flag.
    proc = subprocess.run(
        [sys.executable, str(SKILL / "setup.py"), str(repo), "--refresh-brief"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "refreshed brief:" in proc.stdout
    refreshed = brief_path.read_text(encoding="utf-8")
    assert "Recall: src/pkg/worker.py::process_batch (6-8," in refreshed
    assert "hits=3" in refreshed
    assert "deleted_helper" not in refreshed


def test_sessionstart_hook_contracts_new_vs_resume_and_fail_closed(tmp_path, monkeypatch):
    repo = _make_sample_repo(tmp_path / "repo")
    repo_brief.write_brief(repo)
    subdir = repo / "src" / "pkg"

    def invoke(payload: dict, *, host: str = "copilot", contract: str | None = None, env_off: bool = False) -> dict:
        if env_off:
            monkeypatch.setenv("TOKENMASTER_REPO_BRIEF", "0")
        else:
            monkeypatch.delenv("TOKENMASTER_REPO_BRIEF", raising=False)
        resolved_contract = contract or (
            sessionstart_mod.COPILOT_SESSIONSTART_CONTRACT
            if host == "copilot"
            else sessionstart_mod.CLAUDE_SESSIONSTART_CONTRACT
        )
        monkeypatch.setattr(
            sys,
            "argv",
            ["brainspace_sessionstart.py", "--host", host, "--contract", resolved_contract],
        )
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        rc = sessionstart_mod.main()
        assert rc == 0
        raw_out = out.getvalue().strip()
        return json.loads(raw_out) if raw_out else {}

    # 1. Copilot new session inside nested subdir -> injects additionalContext.
    res_new = invoke(
        {"sessionId": "s-1", "timestamp": 1700000000000, "cwd": str(subdir), "source": "new", "initialPrompt": "hi"}
    )
    assert "additionalContext" in res_new
    assert "src/pkg/core.py::dispatch_event" in res_new["additionalContext"]

    # 2. Copilot resumed session (`source == "resume"`) -> MUST emit `{}` so brief is never duplicated!
    res_resume = invoke({"sessionId": "s-1", "timestamp": 1700000005000, "cwd": str(subdir), "source": "resume"})
    assert res_resume == {}

    # 3. Kill switch `TOKENMASTER_REPO_BRIEF=0` -> `{}`.
    assert invoke(
        {"sessionId": "s-2", "timestamp": 1700000000000, "cwd": str(repo), "source": "new"},
        env_off=True,
    ) == {}

    # 4. Unindexed directory & nested unindexed git repo -> `{}` (does not leak parent repo's brief across `.git`).
    nested_unindexed = repo / "submodules" / "other"
    (nested_unindexed / ".git").mkdir(parents=True)
    assert invoke({"sessionId": "s-3", "timestamp": 1700000000000, "cwd": str(nested_unindexed), "source": "new"}) == {}
    outside = tmp_path / "unindexed"
    outside.mkdir()
    assert invoke({"sessionId": "s-4", "timestamp": 1700000000000, "cwd": str(outside), "source": "new"}) == {}

    # 5. Claude SessionStart startup vs resume envelope.
    claude_start = invoke(
        {"hook_event_name": "SessionStart", "session_id": "c-1", "cwd": str(repo), "source": "startup"},
        host="claude",
    )
    assert claude_start["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "src/pkg/core.py::dispatch_event" in claude_start["hookSpecificOutput"]["additionalContext"]
    assert invoke(
        {"hook_event_name": "SessionStart", "session_id": "c-1", "cwd": str(repo), "source": "resume"},
        host="claude",
    ) == {}

    # 6. Unknown contract or over-budget tampered brief.md -> fails closed `{}`.
    assert invoke(
        {"sessionId": "s-5", "timestamp": 1700000000000, "cwd": str(repo), "source": "new"},
        contract="unknown-contract",
    ) == {}
    (repo / ".token-master" / "brief.md").write_text("word " * 800, encoding="utf-8")
    assert invoke({"sessionId": "s-6", "timestamp": 1700000000000, "cwd": str(repo), "source": "new"}) == {}


def test_copilot_session_hook_ownership_coexistence_and_uninstall(tmp_path):
    view_entry = {"type": "command", "matcher": "view", "exec": "py", "args": ["post.py"], "timeoutSec": 20}
    brief_entry = {"type": "command", "exec": "py", "args": ["brainspace_sessionstart.py"], "timeoutSec": 10}
    foreign = {"type": "command", "exec": "other-tool", "args": ["--init"]}

    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"hooks": {"sessionStart": [foreign]}}), encoding="utf-8")

    wire_copilot_hook(tmp_path, view_entry)
    wire_copilot_session_hook(tmp_path, brief_entry)
    assert copilot_hook_status(tmp_path) is True
    assert copilot_session_hook_status(tmp_path) is True

    parsed = json.loads(settings.read_text(encoding="utf-8"))
    assert parsed["hooks"]["sessionStart"] == [foreign, brief_entry]
    assert parsed["hooks"]["postToolUse"] == [view_entry]

    # Removing sessionStart leaves postToolUse and foreign sessionStart untouched.
    wire_copilot_session_hook(tmp_path, None)
    assert copilot_session_hook_status(tmp_path) is False
    assert copilot_hook_status(tmp_path) is True
    parsed2 = json.loads(settings.read_text(encoding="utf-8"))
    assert parsed2["hooks"]["sessionStart"] == [foreign]
    assert parsed2["hooks"]["postToolUse"] == [view_entry]

    # Hand-edited owned sessionStart hook fails closed.
    wire_copilot_session_hook(tmp_path, brief_entry)
    tampered = json.loads(settings.read_text(encoding="utf-8"))
    tampered["hooks"]["sessionStart"][-1]["timeoutSec"] = 99
    settings.write_text(json.dumps(tampered), encoding="utf-8")
    assert copilot_session_hook_status(tmp_path) is None
    with pytest.raises(ValueError):
        wire_copilot_session_hook(tmp_path, brief_entry)


def test_tokenomics_subtracts_brief_overhead_across_new_and_resumed_launches(tmp_path, monkeypatch):
    repo = _make_sample_repo(tmp_path / "repo")
    meta = repo_brief.write_brief(repo)
    expected_brief = meta["tokens"]
    assert expected_brief > 0

    home = tmp_path / "copilot-home"
    home.mkdir()
    monkeypatch.setenv("COPILOT_HOME", str(home))

    # Configure sessionStart hook in `<COPILOT_HOME>/settings.json`.
    (home / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "sessionStart": [
                        {
                            "type": "command",
                            "exec": sys.executable,
                            "args": [str(SKILL / "brainspace_sessionstart.py"), "--host", "copilot"],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    # Verify `_brief_tokens` measures the exact brief tokens on new launch, 0 when disabled, and inherits on resume.
    monkeypatch.chdir(repo)
    cmd_new = ["copilot", "-p", "check"]
    assert bridge_mod._brief_tokens(cmd_new, {}) == expected_brief
    assert bridge_mod._brief_tokens(cmd_new, {"TOKENMASTER_REPO_BRIEF": "0"}) == 0

    # Seed session store + launches with and without `brief` overhead and verify `tokenomics.summarise` subtracts `brief`.
    db = sqlite3.connect(home / "session-store.db")
    db.execute(
        "create table sessions (id text, cwd text, repository text, branch text, summary text, "
        "created_at text, updated_at text)"
    )
    db.execute(
        "create table assistant_usage_events (id integer primary key, session_id text, agent_id text, model text, "
        "api_endpoint text, input_tokens int, output_tokens int, cache_read_tokens int, cache_write_tokens int, "
        "total_nano_aiu int, token_details_json text, created_at text)"
    )
    db.execute(
        "insert into sessions (id, cwd, repository, created_at) values (?, ?, ?, ?)",
        ("S1", str(repo), "org/repo", "2026-11-17T10:00:05Z"),
    )
    details = json.dumps(
        [
            {"batchSize": 1_000_000, "costPerBatch": int(10 * 1e11), "tokenCount": 100, "tokenType": "input"},
            {"batchSize": 1_000_000, "costPerBatch": int(1 * 1e11), "tokenCount": 7000, "tokenType": "cache_read"},
            {"batchSize": 1_000_000, "costPerBatch": int(50 * 1e11), "tokenCount": 40, "tokenType": "output"},
        ]
    )
    # Two model calls in S1.
    for ts in ("2026-11-17T10:00:10Z", "2026-11-17T10:00:20Z"):
        db.execute(
            "insert into assistant_usage_events (session_id, agent_id, model, api_endpoint, input_tokens, "
            "output_tokens, cache_read_tokens, cache_write_tokens, total_nano_aiu, token_details_json, created_at) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("S1", None, "gpt-6-astra", "/responses", 7100, 40, 7000, 0, int(10_000_000), details, ts),
        )
    db.commit()
    db.close()

    def write_launches(brief_val: int) -> None:
        (home / "token-master").mkdir(exist_ok=True)
        start = {
            "event": "start",
            "id": "L1",
            "at": "2026-11-17T10:00:00Z",
            "cwd": str(repo),
            "lean": True,
            "bridge": False,
            "nav": True,
        }
        if brief_val:
            start["brief"] = brief_val
        end = {"event": "end", "id": "L1", "at": "2026-11-17T10:05:00Z"}
        (home / "token-master" / "launches.jsonl").write_text(
            json.dumps(start) + "\n" + json.dumps(end) + "\n", encoding="utf-8"
        )

    calls_no_brief, sessions = tokenomics_mod.load_store(home / "session-store.db")
    write_launches(0)
    launches_no_brief = tokenomics_mod.load_launches(home / "token-master" / "launches.jsonl")
    tokenomics_mod.estimate(calls_no_brief, sessions, launches_no_brief)
    saved_no_brief = sum(c["saved_tokens"] for c in calls_no_brief)

    calls_with_brief, sessions = tokenomics_mod.load_store(home / "session-store.db")
    write_launches(expected_brief)
    launches_with_brief = tokenomics_mod.load_launches(home / "token-master" / "launches.jsonl")
    tokenomics_mod.estimate(calls_with_brief, sessions, launches_with_brief)
    saved_with_brief = sum(c["saved_tokens"] for c in calls_with_brief)

    # Resume launch inherits the initial session's recorded `brief` overhead.
    assert bridge_mod.recorded_brief("S1") == expected_brief
    assert bridge_mod._brief_tokens(["copilot", "--resume", "S1", "-p", "next"], {}, session="S1") == expected_brief

    # Across 2 calls, subtracting `expected_brief` per call reduces saved_tokens by `2 * expected_brief`.
    assert saved_no_brief - saved_with_brief == 2 * expected_brief


def test_brainspace_setup_copilot_repo_brief_default_on_opt_out_and_guards(tmp_path, monkeypatch):
    from brainspace.tokens import _vocabulary_path

    vocab = _vocabulary_path()
    home = tmp_path / "copilot-home"
    home.mkdir()
    for name in ("HOME", "USERPROFILE", "COPILOT_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.setenv(name, str(tmp_path / name))
    monkeypatch.setenv("COPILOT_HOME", str(home))

    # 1. Non-Copilot host rejects `--copilot-repo-brief` before mutating files.
    monkeypatch.setattr(sys, "argv", ["brainspace_setup.py", "--host", "claude", "--copilot-repo-brief"])
    assert brainspace_setup_mod.main() == 1
    assert not (tmp_path / "CLAUDE_CONFIG_DIR").exists()

    # 2. Default `--host copilot` installs both `postToolUse` and `sessionStart` hooks.
    base = [
        "brainspace_setup.py",
        "--host",
        "copilot",
        "--python",
        sys.executable,
        "--tokenizer-file",
        str(vocab),
    ]
    monkeypatch.setattr(sys, "argv", base)
    assert brainspace_setup_mod.main() == 0
    assert copilot_hook_status(home) is True
    assert copilot_session_hook_status(home) is True
    assert (home / "token-master" / "brainspace_sessionstart.py").is_file()
    assert (home / "token-master" / "brainspace" / "repo_brief.py").is_file()

    # 3. `--no-copilot-repo-brief` removes owned `sessionStart` while keeping `postToolUse`.
    monkeypatch.setattr(sys, "argv", [*base, "--no-copilot-repo-brief"])
    assert brainspace_setup_mod.main() == 0
    assert copilot_session_hook_status(home) is False
    assert copilot_hook_status(home) is True

    # 4. `disableAllHooks: true` skips gracefully by default, and rejects explicit `--copilot-repo-brief`.
    disabled_home = tmp_path / "copilot-disabled"
    disabled_home.mkdir()
    (disabled_home / "settings.json").write_text('{"disableAllHooks": true}', encoding="utf-8")
    monkeypatch.setenv("COPILOT_HOME", str(disabled_home))
    monkeypatch.setattr(
        sys,
        "argv",
        ["brainspace_setup.py", "--host", "copilot", "--python", sys.executable, "--tokenizer-file", str(vocab)],
    )
    assert brainspace_setup_mod.main() == 0
    assert copilot_session_hook_status(disabled_home) is False

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "brainspace_setup.py",
            "--host",
            "copilot",
            "--python",
            sys.executable,
            "--tokenizer-file",
            str(vocab),
            "--copilot-repo-brief",
        ],
    )
    assert brainspace_setup_mod.main() == 1


def test_r1_submodular_monotonicity_diminishing_returns_and_order_invariance():
    """Exhaustively verify F(empty)=0, monotonicity, order-invariance, and submodularity."""
    import random
    from collections import Counter

    rng = random.Random(20261118)
    universe: list[repo_brief.BriefCandidate] = []
    for i in range(14):
        mod = f"pkg/mod_{i % 5}.py"
        parent = "pkg" if i % 3 else "pkg/sub"
        in_files = [f"pkg/caller_{j}.py" for j in range(rng.randint(0, 4)) if rng.random() < 0.6]
        out_files = [f"pkg/callee_{j}.py" for j in range(rng.randint(0, 3)) if rng.random() < 0.5]
        hops = [rng.randint(1, 12) for _ in range(rng.randint(1, 4))]
        atoms = [
            (("sym", ("hub", i)), (100 + 25 * i,)),
            (("mod", mod), repo_brief._MOD_INC_CORE),
            (("dir", parent), repo_brief._DIR_INC),
            *[(("in_file", f), repo_brief._IN_FILE_INC) for f in sorted(set(in_files))],
            *[(("out_file", f), repo_brief._OUT_FILE_INC) for f in sorted(set(out_files))],
            *[(("hop", h), repo_brief._HOP_INC) for h in sorted(set(hops))],
        ]
        universe.append(
            repo_brief.BriefCandidate(
                role=("hub", "recall", "entry")[i % 3],
                sid=i,
                path=mod,
                qualname=f"Sym{i}",
                start=1,
                end=10,
                sym_tokens=80,
                in_degree=len(in_files),
                raw_hits=2,
                recency_score=8,
                is_aux=False,
                line=f"Hub: {mod}::Sym{i} (1-10, ~80t)",
                line_tokens=10 + (i % 5),
                atoms=tuple(atoms),
            )
        )

    assert repo_brief.submodular_value(()) == 0

    for _trial in range(300):
        k_a = rng.randint(0, 6)
        subset_a = rng.sample(universe, k_a)
        remaining = [c for c in universe if c not in subset_a]
        extra = rng.sample(remaining, rng.randint(0, min(4, len(remaining))))
        subset_b = [*subset_a, *extra]
        probes = [c for c in universe if c not in subset_b]
        if not probes:
            continue
        e = rng.choice(probes)

        # Order invariance of F(S).
        shuffled_b = list(subset_b)
        rng.shuffle(shuffled_b)
        val_a = repo_brief.submodular_value(subset_a)
        val_b = repo_brief.submodular_value(subset_b)
        assert val_b == repo_brief.submodular_value(shuffled_b)

        # Monotonicity: A <= B => F(A) <= F(B).
        assert val_a <= val_b

        # Exact consistency between marginal_gain and submodular_value difference.
        counts_a: Counter = Counter()
        for c in subset_a:
            repo_brief._apply_candidate_atoms(c, counts_a)
        counts_b: Counter = Counter()
        for c in subset_b:
            repo_brief._apply_candidate_atoms(c, counts_b)

        gain_a = repo_brief.marginal_gain(e, counts_a)
        gain_b = repo_brief.marginal_gain(e, counts_b)
        assert gain_a == repo_brief.submodular_value([*subset_a, e]) - val_a
        assert gain_b == repo_brief.submodular_value([*subset_b, e]) - val_b
        assert gain_a >= 0 and gain_b >= 0

        # Submodularity (diminishing returns): A <= B => gain(e | A) >= gain(e | B).
        assert gain_a >= gain_b


def test_r1_fold_unfold_bijection_and_collision_safe_read_symbol(tmp_path):
    """Verify syntactic fold/unfold bijection and 1-step SymbolIndex callability under suffix collisions."""
    repo = tmp_path / "deep_repo"
    core = repo / "packages" / " nested " .strip() / "engine" / "src"
    (core / "sub").mkdir(parents=True)
    (repo / "examples").mkdir(parents=True)

    # `termui.py` collides with `examples/termui.py`; `unique_mod.py` does not.
    (core / "termui.py").write_text(
        "def render_banner(msg: str) -> str:\n    return f'[{msg}]'\n",
        encoding="utf-8",
    )
    (repo / "examples" / "termui.py").write_text(
        "def demo() -> str:\n    return 'demo'\n",
        encoding="utf-8",
    )
    for idx_num in range(8):
        (core / "sub" / f"worker_{idx_num}.py").write_text(
            "from ..termui import render_banner\n\n"
            f"def run_worker_{idx_num}(x: str) -> str:\n"
            "    return render_banner(x)\n",
            encoding="utf-8",
        )
    for hub_num in range(6):
        (core / f"service_{hub_num}.py").write_text(
            f"def shared_op_{hub_num}(payload: str) -> str:\n"
            f"    return payload.strip() + ':{hub_num}'\n",
            encoding="utf-8",
        )
    (core / "orchestrator.py").write_text(
        "\n".join(f"from .service_{h} import shared_op_{h}" for h in range(6))
        + "\n\ndef fanout(p: str) -> str:\n    return "
        + " + ".join(f"shared_op_{h}(p)" for h in range(6))
        + "\n",
        encoding="utf-8",
    )
    (core / "cli.py").write_text(
        "from .sub.worker_0 import run_worker_0\n"
        "from .orchestrator import fanout\n"
        + "\n".join(f"from .service_{h} import shared_op_{h}" for h in range(6))
        + "\n\ndef main() -> int:\n"
        "    return len(run_worker_0('a') + fanout('b') + "
        + " + ".join(f"shared_op_{h}('c')" for h in range(6))
        + ")\n",
        encoding="utf-8",
    )

    idx = symbol_index.SymbolIndex(repo)
    try:
        idx.refresh()
        prefix = "packages/nested/engine/src"
        # Pure syntactic round-trip across unique, colliding, and out-of-prefix paths.
        cases = [
            (f"{prefix}/sub/worker_0.py", True, "sub/worker_0.py"),
            (f"{prefix}/termui.py", False, f"/{prefix}/termui.py"),
            ("examples/termui.py", False, "/examples/termui.py"),
        ]
        for full_p, is_uniq, expected_rendered in cases:
            folded = repo_brief.fold_brief_path(prefix, full_p, is_uniq)
            assert folded == expected_rendered
            assert repo_brief.unfold_brief_path(prefix, folded) == full_p
            assert repo_brief.fold_brief_path("", full_p, is_uniq) == full_p
            assert repo_brief.unfold_brief_path("", full_p) == full_p

        # Tight enough budget that `@root=` prefix factoring strictly increases packed F(S).
        text, meta = repo_brief.build_brief(repo, index=idx, budget=190, algorithm="r1")
        assert meta["algorithm"] == "r1"
        assert meta["root_prefix"] == prefix
        assert f"(@root={prefix}/)" in text
        # Colliding `termui.py` MUST be escaped with leading `/` so `read_symbol` is unambiguous!
        assert f"Hub: /{prefix}/termui.py::render_banner" in text

        for line in text.splitlines()[2:]:
            _role, rest = line.split(": ", 1)
            target = rest.split(" (", 1)[0]
            rendered_p, _qual = target.split("::", 1)
            unfolded = repo_brief.unfold_brief_path(meta["root_prefix"], rendered_p)
            out = idx.read(target)
            assert "def " in out and not out.startswith(("[no match", "[ambiguous", "Error:"))
            assert any(r["path"] == unfolded for r in idx._find(target))
    finally:
        idx.close()


def test_r1_prevents_warm_recall_from_starving_entrypoints_and_filters_stale_hub_noise(tmp_path):
    """Under heavy multi-session recall, v1 starves Entry: to 0 while R1 preserves Entry:/Hub: floors and recency."""
    repo = tmp_path / "app_repo"
    pkg = repo / "packages" / "service" / "runtime"
    pkg.mkdir(parents=True)
    (repo / ".token-master").mkdir(parents=True)

    # 4 hub modules + 5 isolated island modules + 3 CLI entrypoints under a deep prefix.
    for h in range(4):
        (pkg / f"hub_{h}.py").write_text(
            f"def core_hub_{h}(val: str) -> str:\n    return val.strip() + '{h}'\n\n"
            f"def second_in_hub_{h}(val: str) -> str:\n    return core_hub_{h}(val)\n",
            encoding="utf-8",
        )
    for m in range(6):
        imports = "\n".join(f"from .hub_{h} import core_hub_{h}, second_in_hub_{h}" for h in range(4))
        calls = " + ".join(f"core_hub_{h}(x) + second_in_hub_{h}(x)" for h in range(4))
        (pkg / f"consumer_{m}.py").write_text(
            f"{imports}\n\ndef process_{m}(x: str) -> str:\n    return {calls}\n",
            encoding="utf-8",
        )
    for isl in range(5):
        (pkg / f"island_{isl}.py").write_text(
            f"class IsolatedSubsystem{isl}:\n"
            "    def compute_metric(self, data: list[int]) -> int:\n"
            f"        return sum(data) + {isl} * 17\n",
            encoding="utf-8",
        )
    for ent in range(3):
        (pkg / f"cli_{ent}.py").write_text(
            f"from .consumer_{ent} import process_{ent}\n"
            f"from .hub_{ent} import core_hub_{ent}\n\n"
            "def main() -> int:\n"
            f"    return len(process_{ent}(core_hub_{ent}('go')))\n",
            encoding="utf-8",
        )

    idx = symbol_index.SymbolIndex(repo)
    try:
        idx.refresh()
        # Older noisy lookups: 3 hits each on top hubs + stale island_0/island_1.
        stale_targets = [
            f"packages/service/runtime/hub_0.py::core_hub_0",
            f"packages/service/runtime/hub_1.py::core_hub_1",
            f"packages/service/runtime/island_0.py::IsolatedSubsystem0",
            f"packages/service/runtime/island_1.py::IsolatedSubsystem1",
        ]
        for target in stale_targets:
            for _ in range(3):
                repo_brief.record_recall(idx, "read_symbol", {"target": target}, idx.read(target))

        # Recent active session lookups (latest 6 events): 2 hits each on island_2, island_3, island_4!
        recent_targets = [
            f"packages/service/runtime/island_2.py::IsolatedSubsystem2",
            f"packages/service/runtime/island_3.py::IsolatedSubsystem3",
            f"packages/service/runtime/island_4.py::IsolatedSubsystem4",
        ]
        for target in recent_targets:
            for _ in range(2):
                repo_brief.record_recall(idx, "read_symbol", {"target": target}, idx.read(target))

        v1_text, v1_meta = repo_brief.build_brief(repo, index=idx, budget=285, algorithm="v1")
        r1_text, r1_meta = repo_brief.build_brief(repo, index=idx, budget=285, algorithm="r1")

        # v1 chops from the tail under tight warm budget -> 0 Entry: lines survive, stale 3-hit islands dominate!
        assert v1_meta["entrypoint_count"] == 0
        assert "Entry: " not in v1_text

        # R1 preserves all 3 role floors (Recall, Hub, Entry) AND surfaces the 3 recent islands!
        assert r1_meta["entrypoint_count"] == 3
        assert r1_meta["hub_count"] >= 3
        assert r1_meta["recall_count"] >= 3
        for recent_cls in ("IsolatedSubsystem2", "IsolatedSubsystem3", "IsolatedSubsystem4"):
            assert recent_cls in r1_text
    finally:
        idx.close()


