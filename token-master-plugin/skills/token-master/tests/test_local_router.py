"""Unit and mathematical-contract tests for R2 local routing, pragmatic deixis & warm-cache Bayes thresholds."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import socket
import sqlite3
import statistics
import sys
import time
import urllib.request
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

from brainspace import local_router, local_router_weights  # noqa: E402
import tokenomics  # noqa: E402

_spec = importlib.util.spec_from_file_location("brainspace_copilot_bridge", SKILL / "brainspace_copilot_bridge.py")
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        "TOKENMASTER_MD1_ENDPOINT",
        "TOKENMASTER_MD1_API_KEY",
        "TOKENMASTER_MD1_THRESHOLD",
        "TOKENMASTER_ROUTER",
        "TOKENMASTER_RESUME_ESCALATE",
        "TOKENMASTER_ESCALATE_MISS_COST",
        "TOKENMASTER_KEEP_TOOLS",
    ):
        monkeypatch.delenv(var, raising=False)


def test_weights_budget_integrity_and_schema_token_alignment():
    weights_file = SKILL / "brainspace" / "local_router_weights.py"
    assert weights_file.stat().st_size < 200 * 1024  # R2 footprint budget (<200 KB; ~24 KB actual)
    raw = zlib.decompress(base64.b85decode(local_router_weights.WEIGHTS_B85))
    assert hashlib.sha256(raw).hexdigest() == local_router_weights.WEIGHTS_SHA256
    payload = json.loads(raw.decode("utf-8"))
    assert set(payload) == set(local_router.FAMILIES) == set(bridge.CAPABILITY_GROUPS)

    for family, (tools, _) in bridge.CAPABILITY_GROUPS.items():
        expected = sum(tokenomics.LEAN_WEIGHTS[t] for t in tools)
        assert local_router.FAMILY_SCHEMA_TOKENS[family] == expected, family


def test_r2_local_scores_are_zero_network_calibrated_and_sub_5ms(monkeypatch):
    def forbid_network(*_args, **_kwargs):
        raise AssertionError("r2_local_scores must never open a socket or HTTP connection")

    monkeypatch.setattr(socket, "create_connection", forbid_network)
    monkeypatch.setattr(urllib.request, "urlopen", forbid_network)

    assert local_router.r2_local_scores("") == {}
    assert local_router.r2_local_scores("   \n\t ") == {}

    local_router.r2_local_scores("warm up index")
    prompts = [
        "have an agent review this diff",
        "did we already try upgrading webpack in an older chat?",
        "fix the null check in OrderService.cs",
        "start the storybook server, leave it running and check /health",
        "audit the workflow weights and background_shell regex in tokenomics.py",
    ]
    timings_ms: list[float] = []
    for p in prompts * 6:
        t0 = time.perf_counter()
        scores = local_router.r2_local_scores(p)
        timings_ms.append((time.perf_counter() - t0) * 1000.0)
        assert set(scores) == set(local_router.FAMILIES)
        for prob in scores.values():
            assert isinstance(prob, float) and 0.0 < prob < 1.0
    assert statistics.median(timings_ms) < 5.0


def test_r2_generalizes_to_held_out_eval_set_without_false_lookalike_keeps():
    eval_path = SKILL.parents[1] / "evals" / "md1_routing_eval.py"
    spec = importlib.util.spec_from_file_location("md1_routing_eval", eval_path)
    md1_eval = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md1_eval)

    tuning_picks = [bridge.r2_families(p) for p, _ in md1_eval.CASES]
    tuning_metrics = md1_eval.score(tuning_picks, md1_eval.CASES)
    assert tuning_metrics["recall"] >= 0.95
    assert tuning_metrics["false_keeps"] == 0

    held_picks = [bridge.r2_families(p) for p, _ in md1_eval.HELD_OUT]
    held_metrics = md1_eval.score(held_picks, md1_eval.HELD_OUT)
    assert held_metrics["recall"] >= 0.90  # >= 90% unseen recall (vs 38.5% static regex)
    assert held_metrics["false_keeps"] <= 1
    assert held_metrics["no_need_prompts_kept_nothing"] == "9/9"


def test_pragmatic_discourse_deixis_separates_intra_from_cross_session():
    base = {fam: 0.02 for fam in local_router.FAMILIES}
    base["session_history"] = 0.92
    base["agents"] = 0.94

    # Turn 1 (not resumed): never suppresses session_history.
    t1 = local_router.apply_discourse_deixis(base, "Summarize what happened in Turn 1", is_resumed=False)
    assert t1["session_history"] == pytest.approx(0.92)

    # Resumed intra-session synthesis ("Turn 1 and Turn 2", "you recorded"): suppresses session_history, keeps agents!
    intra_prompts = [
        "Combine the exact calibration values you recorded in Turn 1 and Turn 2 into a single JSON object.",
        "Using the counts from the first turn, format a markdown table.",
        "Check whether the threshold you just found earlier in this session matches 0.5.",
    ]
    for p in intra_prompts:
        assert local_router.is_intra_session_deixis(p), p
        updated = local_router.apply_discourse_deixis(base, p, is_resumed=True)
        assert updated["session_history"] < 0.05, p
        assert updated["agents"] == pytest.approx(0.94), p

    # Resumed cross-session recall (even when also mentioning Turn 1!): must NOT suppress session_history!
    cross_prompts = [
        "Compare the values you recorded in Turn 1 with yesterday's session.",
        "Did we already fix this migration in an older chat?",
        "Look through my previous sessions for the deploy command.",
        "Pull up what we decided on Monday about the cache.",
    ]
    for p in cross_prompts:
        assert not local_router.is_intra_session_deixis(p), p
        updated = local_router.apply_discourse_deixis(base, p, is_resumed=True)
        assert updated["session_history"] == pytest.approx(0.92), p


def test_bayes_escalation_threshold_identities_and_monotonicity():
    cold = local_router.CacheState(launch_num=2, warm_cached_tokens=0, at_risk_tokens=0)
    launch2 = local_router.CacheState(launch_num=2, warm_cached_tokens=36000, at_risk_tokens=3649)
    launch3 = local_router.CacheState(launch_num=3, warm_cached_tokens=36000, at_risk_tokens=36000)

    # Exact cold & boundary identities
    for fam in local_router.FAMILIES:
        assert local_router.bayes_escalation_threshold(0.5, None, fam) == 0.5
        assert local_router.bayes_escalation_threshold(0.5, cold, fam) == 0.5
        assert local_router.bayes_escalation_threshold(0.0, launch3, fam) == 0.0
        assert local_router.bayes_escalation_threshold(1.0, launch3, fam) == 1.0

    # Prefix monotonicity: cold (0.50) < Launch 2 (~0.63) < Launch 3 (~0.88) < 1.0
    for fam in local_router.FAMILIES:
        t_cold = local_router.bayes_escalation_threshold(0.5, cold, fam)
        t_l2 = local_router.bayes_escalation_threshold(0.5, launch2, fam)
        t_l3 = local_router.bayes_escalation_threshold(0.5, launch3, fam)
        assert 0.5 == t_cold < t_l2 < t_l3 < 1.0

    # Schema-weight monotonicity across families at positive risk
    ordered_fams = sorted(local_router.FAMILIES, key=lambda f: local_router.FAMILY_SCHEMA_TOKENS[f])
    thresholds = [local_router.bayes_escalation_threshold(0.5, launch2, f) for f in ordered_fams]
    assert thresholds == sorted(thresholds)
    assert thresholds[0] < thresholds[-1]


def test_session_cache_state_reads_two_stage_risk_and_expiry(tmp_path):
    home = tmp_path / "copilot"
    home.mkdir()
    db_path = home / "session-store.db"
    now = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)

    conn = sqlite3.connect(db_path)
    conn.execute(
        "create table assistant_usage_events ("
        "id text primary key, session_id text, created_at text, "
        "cache_read_tokens integer, cache_write_tokens integer, token_details_json text, agent_id text)"
    )
    details = json.dumps([
        {"tokenType": "input", "costPerBatch": 3.0, "batchSize": 1000},
        {"tokenType": "cache_read", "costPerBatch": 0.3, "batchSize": 1000},
        {"tokenType": "cache_write", "costPerBatch": 3.75, "batchSize": 1000},
    ])
    # Main call 40s ago with 34,000 cached tokens + newer subagent call with tiny prefix (must be ignored)
    conn.execute(
        "insert into assistant_usage_events values (?, ?, ?, ?, ?, ?, ?)",
        ("u1", "s-warm", (now - timedelta(seconds=40)).isoformat(), 31000, 3000, details, None),
    )
    conn.execute(
        "insert into assistant_usage_events values (?, ?, ?, ?, ?, ?, ?)",
        ("u2", "s-warm", (now - timedelta(seconds=10)).isoformat(), 1200, 0, details, "subagent-1"),
    )
    # Expired call 8 minutes ago
    conn.execute(
        "insert into assistant_usage_events values (?, ?, ?, ?, ?, ?, ?)",
        ("u3", "s-cold", (now - timedelta(minutes=8)).isoformat(), 40000, 0, details, ""),
    )
    conn.commit()
    conn.close()

    # Launch 2 caps at-risk tokens at STATIC_LEAN_PREFIX (3,649)
    st_l2 = local_router.session_cache_state("s-warm", copilot_home=home, prior_launches=1, now=now)
    assert st_l2.launch_num == 2
    assert st_l2.warm_cached_tokens == 34000
    assert st_l2.at_risk_tokens == local_router.STATIC_LEAN_PREFIX
    assert st_l2.write_premium == pytest.approx(1.15)

    # Launch 3 exposes full 34,000 cached tokens
    st_l3 = local_router.session_cache_state("s-warm", copilot_home=home, prior_launches=2, now=now)
    assert st_l3.launch_num == 3
    assert st_l3.at_risk_tokens == 34000

    # Expired session (>5 min) resets to 0 at-risk tokens
    st_exp = local_router.session_cache_state("s-cold", copilot_home=home, prior_launches=2, now=now)
    assert st_exp.at_risk_tokens == 0


def test_bridge_r2_stateful_resume_blocks_warm_false_breaks_and_preserves_escalations(tmp_path, monkeypatch):
    home = tmp_path / "copilot-home"
    (home / "session-state").mkdir(parents=True)
    monkeypatch.setenv("COPILOT_HOME", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.delenv("COPILOT_PROVIDER_BASE_URL", raising=False)
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)

    conn = sqlite3.connect(home / "session-store.db", isolation_level=None)
    conn.execute("create table sessions (id text primary key, cwd text, repository text, created_at text, updated_at text)")
    conn.execute(
        "create table assistant_usage_events ("
        "id text primary key, session_id text, created_at text, "
        "cache_read_tokens integer, cache_write_tokens integer, token_details_json text, agent_id text)"
    )
    commands: list[list[str]] = []
    sid = "11111111-2222-4333-8444-555555555555"

    def stamp(after: str = "") -> str:
        while True:
            now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            if now > after:
                return now
            time.sleep(0.001)

    def fake_run(_parser, cmd, _env):
        commands.append(cmd)
        reg = bridge.launch_registry()
        after = json.loads(reg.read_text(encoding="utf-8").splitlines()[-1]).get("at", "") if reg.is_file() else ""
        ts = stamp(after)
        if "--resume" not in cmd:
            (home / "session-state" / sid).mkdir(exist_ok=True)
            conn.execute("insert into sessions values (?, ?, ?, ?, ?)", (sid, str(tmp_path), None, ts, ts))
            conn.execute(
                "insert into assistant_usage_events values (?, ?, ?, ?, ?, ?, ?)",
                ("call-1", sid, ts, 32000, 4000, None, None),
            )
        else:
            conn.execute("update sessions set updated_at = ? where id = ?", (ts, sid))
            conn.execute(
                "insert into assistant_usage_events values (?, ?, ?, ?, ?, ?, ?)",
                (f"call-{len(commands)}", sid, ts, 36000, 1500, None, None),
            )
        return 0

    def excluded_of(cmd: list[str]) -> set[str]:
        return set(cmd[cmd.index("--excluded-tools") + 1:]) if "--excluded-tools" in cmd else set()

    monkeypatch.setattr(bridge, "run_child", fake_run)
    lean = set(bridge.LEAN_EXCLUDED_TOOLS)
    agents = set(bridge.CAPABILITY_GROUPS["agents"][0])

    # Turn 1: pure coding prompt under local R2 router -> all 13 auxiliary tools excluded
    bridge.main(["--lean", "--router", "r2", "--resume-escalate", "r2", "--", "copilot", "-p",
                 "Read tokenomics.py and record STATIC_LEAN_PREFIX."])
    assert excluded_of(commands[-1]) == lean

    # Turn 2 (Launch 2, warm 3,649 at-risk): indirect multi-worker prompt -> unlocks agents cleanly
    bridge.main(["--lean", "--router", "r2", "--resume-escalate", "r2", "--", "copilot", "--resume", sid, "-p",
                 "Spin up two helper workers in parallel to inspect symbol_index.py and v6_shaping.py."])
    assert excluded_of(commands[-1]) == lean - agents

    # Turn 3 (Launch 3, warm 37,500 at-risk): intra-session Turn 1 & Turn 2 synthesis -> NO session_history break!
    bridge.main(["--lean", "--router", "r2", "--resume-escalate", "r2", "--", "copilot", "--resume", sid, "-p",
                 "Combine the exact numbers you recorded in Turn 1 and Turn 2 into one JSON object."])
    assert excluded_of(commands[-1]) == lean - agents
    assert "session_store_sql" in excluded_of(commands[-1])

    # Contrast v1 vs r2 on warm Launch 4 (~37,500 cached tokens, tau* ~ 0.88) for a marginal 0.65 posterior:
    marginal = {fam: 0.01 for fam in local_router.FAMILIES}
    marginal["workflows"] = 0.65
    monkeypatch.setattr(bridge, "r2_local_scores", lambda _p: dict(marginal))
    # r2 blocks the expensive 37.5k cache break when posterior 0.65 < tau* (~0.88):
    bridge.main(["--lean", "--router", "r2", "--resume-escalate", "r2", "--", "copilot", "--resume", sid, "-p",
                 "check workflow config"])
    assert "run_dynamic_workflow" in excluded_of(commands[-1])
    # whereas stateless v1 (flat 0.50 threshold) breaks the warm cache on the exact same 0.65 posterior:
    bridge.main(["--lean", "--router", "r2", "--resume-escalate", "v1", "--", "copilot", "--resume", sid, "-p",
                 "check workflow config"])
    assert "run_dynamic_workflow" not in excluded_of(commands[-1])


def test_brainspace_setup_installs_local_router_and_weights(tmp_path):
    import brainspace_setup

    installed = brainspace_setup._install_files(tmp_path / "copilot-home")
    assert (installed / "brainspace" / "local_router.py").is_file()
    assert (installed / "brainspace" / "local_router_weights.py").is_file()


def test_cross_session_deixis_survives_long_schema_tails_and_ignores_quoted_code_literals():
    long_cross_query = (
        "Query earlier sessions in `session_store_sql` (do not touch `.db` files via shell) to find "
        "the agreed snapshot retention window in days and compression codec, and combine them with "
        "Turn 1 and Turn 2 into ONLY a JSON object with keys `max_loose` (int), `max_title` (int), "
        "`retention_days` (int), and `compression` (str)."
    )
    assert local_router.has_cross_session_deixis(long_cross_query)
    assert not local_router.is_intra_session_deixis(long_cross_query)
    scores = local_router.r2_local_scores(long_cross_query)
    warm_l3 = local_router.CacheState(launch_num=3, warm_cached_tokens=7074, at_risk_tokens=7074)
    tau_sh = local_router.bayes_escalation_threshold(0.5, warm_l3, "session_history")
    resumed_scores = local_router.apply_discourse_deixis(scores, long_cross_query, is_resumed=True)
    assert resumed_scores["session_history"] > tau_sh

    # Quoted dictionary keys / function arguments in code-inspection prompts must NOT trigger cross-session deixis.
    quoted_dict_key = (
        "Inspect `tokenomics.py` without editing files and read the exact integer weights in "
        "`LEAN_WEIGHTS` for `'task'`, `'sql'`, `'skill'`, and `'session_store_sql'`."
    )
    quoted_func_arg = (
        "Verify with Python that `is_allowed_native_field('prompt_cache_key')` is `True` and "
        "`is_allowed_native_field('session_history')` is `False` from the previous turn's edit."
    )
    assert not local_router.has_cross_session_deixis(quoted_dict_key)
    assert local_router.r2_local_scores(quoted_dict_key)["session_history"] < 0.20

    assert not local_router.has_cross_session_deixis(quoted_func_arg)
    assert local_router.is_intra_session_deixis(quoted_func_arg)
    resumed_arg = local_router.apply_discourse_deixis(
        local_router.r2_local_scores(quoted_func_arg), quoted_func_arg, is_resumed=True
    )
    assert resumed_arg["session_history"] < 0.05


