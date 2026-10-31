"""The code satisfies the hypotheses of the Lean proofs in proofs/TokenMasterProofs.

The Lean theorems are about models. Each test here checks that the real function behaves as its
model says, on generated inputs and on the recorded study data, and names the theorem it supports.
Tests named test_finding_* reproduce a gap that proofs/README.md reports; if one starts failing,
the gap was fixed, and the README's findings need the same update.
"""
from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brainspace_copilot_bridge as bridge  # noqa: E402
import tokenomics  # noqa: E402
from brainspace import native_transport, runtime, symbol_index, tokens, v6_shaping  # noqa: E402
from brainspace.request_policy import (  # noqa: E402
    RequestPlan, RequestPolicy, TransformResult, plan_request, serialize_request)
from brainspace.runtime import RuntimeSession  # noqa: E402
from brainspace.transport import Reply, ResponsesTransport  # noqa: E402

SKILL = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
STUDY = REPO / "evidence" / "default-routing-20261027"
BS = "\\"
V6 = RequestPolicy(version="request-policy-v6", enabled=True)

# Routing.Group.tools, in Routing.Group.all order.
FAMILIES = {"session_history": ("session_store_sql",), "agents": ("task", "read_agent", "write_agent", "list_agents"),
            "skills": ("skill",), "sql": ("sql",),
            "background_shell": ("read_powershell", "stop_powershell", "list_powershell"),
            "copilot_docs": ("fetch_copilot_cli_documentation",),
            "workflows": ("run_dynamic_workflow", "dynamic_workflows_manage")}
LEAN_MODEL = tuple(tool for tools in FAMILIES.values() for tool in tools)
CORE = ("view", "edit", "create", "rg", "glob", "powershell", "report_intent")
TRIGGERS = {"session_history": "look at previous sessions", "agents": "spawn an agent for this",
            "skills": "use the review skill", "sql": "run a sql query", "copilot_docs": "check the copilot cli docs",
            "background_shell": "start the server in the background", "workflows": "run my_audit_workflow"}

_NOTICE = re.compile(r"^\[.*\]$")
_ENTRY = re.compile(r"^  ([0-9]+)([:-]) (.*)$")


def exact_counter():
    if not tokens.backend_info()["exact_reference"]:
        pytest.skip("no verified cl100k_base vocabulary")
    return tokens.count_tokens


@pytest.fixture
def fallback_counter(monkeypatch):
    """tokens.estimate as it runs without the vocabulary: ceil(characters / 4)."""
    monkeypatch.setattr(tokens, "_TRIED", True)
    monkeypatch.setattr(tokens, "_ENCODER", None)
    return tokens.estimate


@pytest.fixture
def no_installed_assets(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "copilot-home"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))  # no Copilot CLI package: no built-in skills
    monkeypatch.delenv("COPILOT_SKILLS_DIRS", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()  # a repository root: Copilot CLI's skill folders above it are not read
    monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", "")


def test_routing_lists_match_the_lean_model():
    """Routing.Group.tools, Routing.leanExcluded and Routing.core name exactly these tools, family by family."""
    assert {group: tools for group, (tools, _) in bridge.CAPABILITY_GROUPS.items()} == FAMILIES
    assert tuple(bridge.CAPABILITY_GROUPS) == tuple(FAMILIES)
    assert bridge.LEAN_EXCLUDED_TOOLS == LEAN_MODEL
    assert not set(CORE) & set(LEAN_MODEL)


def test_routing_fired_families_are_kept(no_installed_assets):
    """Routing.fired_family_kept and Routing.excluded_subset_lean, for each family's prompt trigger."""
    for group, prompt in TRIGGERS.items():
        excluded = bridge.select_excluded_tools(["copilot", "-p", prompt])
        assert set(excluded) <= set(LEAN_MODEL)
        assert not set(FAMILIES[group]) & set(excluded), group


def test_routing_flags_environment_and_workflows(no_installed_assets, monkeypatch):
    """Routing.fired_family_kept for --agent, --fleet, --resume and -r, Routing.env_tool_kept,
    Routing.workflows_follow_skill and Routing.agents_follow_skill."""
    assert not set(FAMILIES["agents"]) & set(bridge.select_excluded_tools(["copilot", "--agent", "x"]))
    assert not {"sql", *FAMILIES["agents"]} & set(bridge.select_excluded_tools(["copilot", "--fleet"]))
    for flag in ("--resume", "-r"):
        assert "session_store_sql" not in bridge.select_excluded_tools(["copilot", flag])
    monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", "sql,skill")
    excluded = bridge.select_excluded_tools(["copilot"])
    assert not {"sql", "skill", "run_dynamic_workflow", "dynamic_workflows_manage", *FAMILIES["agents"]} & set(excluded)


def test_routing_nothing_fires_excludes_all(no_installed_assets):
    """Routing.nothing_fires_excludes_all."""
    assert bridge.select_excluded_tools(["copilot", "-p", "fix the failing test in parser.py"]) == LEAN_MODEL


def test_finding_routing_patterns_miss_some_phrasings(no_installed_assets):
    """Findings: the theorems keep a family whose trigger fires; this request for an agent fires none."""
    assert "task" in bridge.select_excluded_tools(["copilot", "-p", "have an agent review this diff"])


def test_routing_resume_keeps_the_first_list(no_installed_assets, tmp_path, monkeypatch):
    """Routing.resume_same_list and Routing.resume_chain_keeps_first_list, on main() with a stand-in for Copilot CLI:
    a session started with each trigger's prompt gets its first list back on every resume, whatever the resume's own
    prompt. Routing.resumed_env_kept: a tool TOKENMASTER_KEEP_TOOLS names is kept on a resume too.
    Routing.resumed_subset_lean: a recorded tool outside LEAN_EXCLUDED_TOOLS is not excluded.
    Routing.resume_without_record: a session no launch recorded is routed as before. And
    Routing.default_excludes_nothing: a session with a recorded list, resumed without --lean, gets every tool."""
    home = tmp_path / "copilot-home"
    (home / "session-state").mkdir(parents=True)
    store = sqlite3.connect(home / "session-store.db", isolation_level=None)
    store.execute("create table sessions (id text primary key, cwd text, repository text, created_at text, "
                  "updated_at text)")
    sent = []

    def now(after=""):  # to the millisecond, as Copilot CLI writes it, and later than `after`: the clock can step 15.6 ms
        while (stamp := datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")) <= after:
            time.sleep(0.001)
        return stamp

    def copilot(parser, command, env):  # starts a session unless the command resumes one, after the last launch record
        sent.append(command)
        if "--resume" not in command:
            session = f"{len(sent):08d}-0000-4000-8000-000000000000"
            (home / "session-state" / session).mkdir()
            started = now(json.loads(bridge.launch_registry().read_text(encoding="utf-8").splitlines()[-1])["at"])
            store.execute("insert into sessions values (?, ?, ?, ?, ?)", (session, os.getcwd(), None, started, started))
        return 0

    def excluded(command):
        return command[command.index("--excluded-tools") + 1:] if "--excluded-tools" in command else []

    monkeypatch.delenv("COPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.setattr(bridge, "run_child", copilot)
    for prompt in TRIGGERS.values():
        bridge.main(["--lean", "--", "copilot", "-p", prompt])
        session, first = f"{len(sent):08d}-0000-4000-8000-000000000000", excluded(sent[-1])
        assert first == list(bridge.select_excluded_tools(["copilot", "-p", prompt]))
        for other in TRIGGERS.values():
            bridge.main(["--lean", "--", "copilot", "--resume", session, "-p", other])
            assert excluded(sent[-1]) == first, (prompt, other)
    monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", "background_shell")
    bridge.main(["--lean", "--", "copilot", "--resume", session])
    assert excluded(sent[-1]) == [tool for tool in first if tool not in FAMILIES["background_shell"]] != first
    monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", "")
    edited = {"event": "start", "id": "edited", "at": now(), "cwd": os.getcwd(), "lean": True,
              "excluded": ["view", "sql", "powershell"], "session": session}
    for event in (edited, {"event": "end", "id": "edited", "at": now()}):
        bridge._record_launch(event)
    bridge.main(["--lean", "--", "copilot", "--resume", session])
    assert excluded(sent[-1]) == ["sql"]
    copilot(None, ["copilot"], {})  # a session started without the launcher
    command = ["copilot", "--resume", f"{len(sent):08d}-0000-4000-8000-000000000000", "-p", "spawn an agent for this"]
    bridge.main(["--lean", "--", *command])
    assert excluded(sent[-1]) == list(bridge.select_excluded_tools(command))
    earlier = "00000001-0000-4000-8000-000000000000"  # started and resumed with --lean, so its list is recorded
    bridge.main(["--", "copilot", "--resume", earlier])
    assert sent[-1] == ["copilot", "--resume", earlier]  # Routing.default_excludes_nothing, with a record
    store.close()


def test_routing_default_sends_every_tool(no_installed_assets, monkeypatch):
    """Routing.default_excludes_nothing and Routing.lean_launch_is_routed, on main(): without --lean the command reaches
    Copilot CLI unchanged, whatever the prompt, flags or TOKENMASTER_KEEP_TOOLS, so every built-in tool is sent; with
    --lean it gets the routed --excluded-tools."""
    sent = []
    monkeypatch.delenv("COPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.setattr(bridge, "run_child", lambda parser, command, env: sent.append(command) or 0)
    for keep in ("", "sql"):
        monkeypatch.setenv("TOKENMASTER_KEEP_TOOLS", keep)
        for prompt in TRIGGERS.values():
            for flags in ([], ["--resume", "abcdef12"], ["--continue"], ["--agent", "x"]):
                command = ["copilot", *flags, "-p", prompt]
                bridge.main(["--", *command])
                assert sent[-1] == command
                bridge.main(["--lean", "--", *command])
                routed = list(bridge.select_excluded_tools(command))
                assert sent[-1] == ([*command, "--excluded-tools", *routed] if routed else command)


def _unfold_paths(text: str) -> str:
    """Folds.unfoldPaths: an indented line is a name, an empty line or a notice passes through, and any
    other line is a head."""
    out, current = [], ""
    for line in text.split("\n"):
        if line.startswith("  "):
            out.append(current + line[2:])
        elif not line or _NOTICE.match(line):
            out.append(line)
        else:
            current = "" if line == "." else line
    return "\n".join(out)


def _unfold_search(text: str) -> str:
    """Folds.unfoldSearch: a non-entry line is a header when an entry follows it."""
    lines, out, current = text.split("\n"), [], None
    for index, line in enumerate(lines):
        entry = _ENTRY.match(line)
        if entry:
            num, sep, rest = entry.groups()
            out.append(current + sep + num + sep + rest if current is not None else line)
        elif index + 1 < len(lines) and _ENTRY.match(lines[index + 1]):
            current = line
        else:
            out.append(line)
            current = None
    return "\n".join(out)


def _head(entry: str) -> str:
    """The head fold_paths prints for an entry, computed as fold_paths computes it."""
    bare = entry.rstrip("\\/")
    return entry[:max(bare.rfind("\\"), bare.rfind("/")) + 1]


def _path_list(rng: random.Random) -> str:
    folders = ["src", "src/app", "tests", f"C:{BS}work{BS}repo", "docs/api v2", "a/b/c", ""]
    names = ["main.py", "util.py", "lib.rs", "README.md", "data.json", "mod.py:12", "app/"]
    entries = []
    for _ in range(rng.randint(3, 25)):
        folder = rng.choice(folders)
        sep = BS if BS in folder else "/"
        entries.append((folder + sep if folder else rng.choice(["x/", "y" + BS])) + rng.choice(names))
    if rng.random() < 0.7:  # glob output usually lists a folder's files together
        entries.sort(key=lambda entry: _head(entry))
    notices = ["[Output truncated: 3 more paths]"] if rng.random() < 0.3 else []
    return "\n".join(entries + notices) + "\n" * rng.randint(0, 2)


def _search_output(rng: random.Random, entry_like: float = 0.0, odd_path: float = 0.0) -> str:
    paths = ["src/app.py", "tests/test_app.py", f"C:{BS}repo{BS}mod.rs", "lib/a-b.py", "src/app.py.bak"]
    texts = ["x = 1", "def f(a, b):", "  return a-b", "url = 'http://x:80/a'", "", 't = "10:30:00"', "-9- y"]
    lines = []
    for _ in range(rng.randint(3, 40)):
        roll, path, number, text = rng.random(), rng.choice(paths), rng.randint(1, 999), rng.choice(texts)
        if roll < odd_path:
            lines.append(f"  {number}- word:{rng.randint(1, 99)}:{text}")  # a match line whose path looks like an entry
        elif roll < odd_path + entry_like:
            lines.append(f"  {number}: {text}")
        elif roll < 0.6:
            lines.append(f"{path}:{number}:{text}")
        elif roll < 0.9:
            lines.append(f"{path}-{number}-{text}")
        else:
            lines.append(rng.choice(("--", "binary file matches", "no match")))
    return "\n".join(lines)


def test_fold_paths_round_trip():
    """Folds.unfoldPaths_foldPaths: unfolding gives back the exact input, trailing newlines included.
    Folds.GoodEntry rests on _PATH refusing an entry that starts with whitespace, so inputs with one must not fold."""
    rng, folded_any, refused = random.Random(11), 0, 0
    for _ in range(2000):
        text = _path_list(rng)
        if rng.random() < 0.15:
            lines = text.split("\n")
            lines.insert(rng.randrange(len(lines)), "  " + rng.choice(("src/x.py", "a/b/c.rs", "y.md")))
            text = "\n".join(lines)
        folded = v6_shaping.fold_paths(text)
        if any(line[:1].isspace() for line in text.split("\n")):
            assert folded is None
            refused += 1
            continue
        if folded is None:
            continue
        folded_any += 1
        assert _unfold_paths(folded) == text
    assert folded_any > 300 and refused > 100


def test_fold_search_round_trip():
    """Folds.unfold_foldSearchChecked: whenever fold_search folds, unfolding gives back the input exactly, and it
    refuses any input with a copied line that looks like an entry. Folds.OwnedWellFormed rests on _SUSPECT_PATH:
    the generator adds match lines whose path looks like an entry, and only that guard keeps such a path from
    owning lines, so removing it makes the refusal check below fail."""
    rng, folded_any, refused = random.Random(12), 0, 0
    for _ in range(3000):
        text = _search_output(rng, entry_like=0.03, odd_path=0.03)
        folded = v6_shaping.fold_search(text)
        if any(_ENTRY.match(line) for line in text.split("\n")):
            assert folded is None, text
            refused += 1
            continue
        if folded is None:
            continue
        folded_any += 1
        assert _unfold_search(folded) == text
    assert folded_any > 200 and refused > 300


def test_fold_search_refuses_entry_like_copied_lines():
    """Folds.foldSearch_not_injective: without the refusal these two inputs fold to the same text. fold_search
    now refuses the first and folds the second losslessly."""
    copied = "longpath.py:1:a\nlongpath.py:2:b\n  3: c"
    owned = "longpath.py:1:a\nlongpath.py:2:b\nlongpath.py:3:c"
    assert v6_shaping.fold_search(copied) is None
    assert _unfold_search(v6_shaping.fold_search(owned)) == owned


def _view_text(rng: random.Random) -> str:
    body = []
    for i in range(rng.randint(400, 1500)):
        body.append(f"def function_{i}(argument):" if i % 9 == 0 else f"    value_{i} = argument * {i}  # {'x' * (i % 40)}")
    return "\n".join(body)


def _escaped(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def test_shaped_results_never_expand():
    """Shaping.guard_never_expands (tokens and bytes) and Shaping.guard_strict_if_changed, on shape_tool_result
    itself."""
    rng, count, changed = random.Random(13), tokens.estimate, 0
    cases = ([("rg", {"pattern": "x"}, _search_output(rng) * 20) for _ in range(30)]
             + [("glob", {"pattern": "**/*"}, _path_list(rng) * 30) for _ in range(30)]
             + [("view", {"path": "big.py"}, _view_text(rng)) for _ in range(10)]
             + [("view", {"path": "big.py", "view_range": [1, 9]}, _view_text(rng)) for _ in range(3)]
             + [("custom_tool", {}, "x" * 20000), ("rg", {}, "Error: no such file")])
    for name, arguments, content in cases:
        shaped = v6_shaping.shape_tool_result(name, arguments, content, count)
        assert shaped == v6_shaping.shape_tool_result(name, arguments, content, count)
        if shaped != content:
            changed += 1
            assert count(shaped) < count(content)
            assert v6_shaping._wire_size(shaped) <= v6_shaping._wire_size(content)
        if "view_range" in arguments or content.startswith("Error"):
            assert shaped == content
    assert changed > 30


def _chat_request(items: list[tuple[str, dict, str]], model: str = "fixture") -> dict:
    messages = [{"role": "user", "content": "go"}]
    for index, (name, arguments, content) in enumerate(items):
        messages += [{"role": "assistant", "content": None, "tool_calls": [{"id": f"c{index}", "type": "function",
                      "function": {"name": name, "arguments": json.dumps(arguments)}}]},
                     {"role": "tool", "tool_call_id": f"c{index}", "content": content}]
    return {"model": model, "messages": messages}


def test_v6_keeps_a_fold_that_saves_raw_tokens():
    """The glob output the old whole-request check reverted: it saves tokens on the decoded text, the text a provider
    bills, but none on the escaped JSON wire, and plan_request with v6 now keeps it."""
    count = exact_counter()
    output = f"C:{BS}work{BS}repo{BS}lib.rs\nC:{BS}work{BS}repo{BS}util.py\ntests/data.json"
    shaped = v6_shaping.shape_tool_result("glob", {}, output, count)
    assert shaped != output and count(shaped) < count(output)
    assert count(_escaped(shaped)) >= count(_escaped(output))
    plan = plan_request(_chat_request([("glob", {}, output)]), policy=V6, protocol="chat-completions-v1", count=count)
    assert plan.status == "transformed"


def test_v6_shapes_regardless_of_stable_prefix():
    """Policy.protected_unchanged covers v1 to v4. v6 shapes every tool result, the stable prefix included;
    Cache.shaping_prefix_stable is why that keeps the cache: each message is shaped the same way on every call."""
    content = _search_output(random.Random(5)) * 20
    request = _chat_request([("rg", {"pattern": "x"}, content), ("rg", {"pattern": "x"}, content)])
    plan = plan_request(request, policy=RequestPolicy(version="request-policy-v6", enabled=True, keep_recent_tool_results=1),
                        protocol="chat-completions-v1", count=tokens.estimate, stable_prefix_messages=len(request["messages"]))
    assert plan.status == "transformed" and 4 in plan.changed_message_indices


def _tool_output(rng: random.Random) -> tuple[str, dict, str]:
    roll = rng.random()
    if roll < 0.35:
        return "glob", {}, _path_list(rng) * rng.choice((1, 3))
    if roll < 0.7:
        return "rg", {"pattern": "x"}, _search_output(rng) * rng.choice((1, 4))
    if roll < 0.85:
        return "view", {"path": "big.py"}, _view_text(rng)
    return "glob", {}, "\n".join(f"C:{BS}work{BS}repo{BS}f{rng.randint(0, 9)}.py" for _ in range(rng.randint(3, 12)))


def test_v6_plans_keep_earlier_messages():
    """Cache.shaping_prefix_stable, on plan_request with v6 across growing sessions: every plan starts with the
    previous plan's messages. Also Shaping.billed_tokens_shrink_if_additive: the cl100k count of the tool messages'
    decoded text, the text a provider bills, never grows, and shrinks whenever a plan changes something."""
    count, rng, plans, changed = exact_counter(), random.Random(19), 0, 0
    for _ in range(40):
        items, previous = [], None
        for _ in range(6):
            items.append(_tool_output(rng))
            plan = plan_request(_chat_request(items), policy=V6, protocol="chat-completions-v1", count=count)
            messages = plan.request["messages"]
            if previous is not None:
                assert messages[:len(previous)] == previous
            previous = messages
            plans += 1
            billed = [sum(count(m["content"]) for m in r["messages"] if m["role"] == "tool")
                      for r in (_chat_request(items), plan.request)]
            assert billed[1] < billed[0] if plan.status == "transformed" else billed[1] == billed[0]
            changed += plan.status == "transformed"
    assert plans == 240 and changed > 100


@pytest.mark.parametrize("capped", [False, True])
def test_runtime_keeps_v6_shaping(tmp_path, monkeypatch, capped):
    """The runtime keeps v6 shaping when only the whole request's token count is not smaller, so
    Cache.shaping_prefix_stable holds on the native runtime path too. When the shaped request would exceed
    max_input_tokens and the original fits, it sends the original, as before, instead of failing the call."""
    def send(self, wire):
        body = {"object": "response", "status": "completed", "model": self.model, "output": [],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}
        return Reply(True, "ok", True, wire, json.dumps(body), body, 200)

    def prepare(request, policy, **kwargs):  # a shaped message with fewer bytes and more tokens
        candidate = json.loads(json.dumps(request))
        index = next(i for i, m in enumerate(candidate["messages"]) if m["role"] == "tool")
        candidate["messages"][index]["content"] = "".join(random.Random(33).choice("~^`|q") for _ in range(900))
        return RequestPlan(candidate, None, "transformed", "cache_native_shaping_v6", policy.policy_id, (index,))

    monkeypatch.setattr(ResponsesTransport, "send", send)
    monkeypatch.setattr(runtime, "prepare_request", prepare)
    (tmp_path / "workspace").mkdir()
    transport = ResponsesTransport(base_url="http://127.0.0.1:1/x", model="offline-fixture")
    request = _chat_request([("read_file", {"path": "a.txt"}, "word " * 200), ("read_file", {"path": "b.txt"}, "recent")],
                            model="offline-fixture")
    cap = tokens.count_tokens(transport.encode(request)) if capped else None
    session = RuntimeSession(workspace=tmp_path / "workspace", output=tmp_path / "out", session_id="v6", backend="local",
                             policy=replace(V6, max_input_tokens=cap), transport=transport)
    session.invoke(request)
    row = json.loads((tmp_path / "out" / "preparations.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    if capped:
        assert not row["changed_messages"] and row["reason"] == "final_wire_guard_reversion"
        assert row["reference_after"] == cap
    else:
        assert row["changed_messages"] and row["reason"] == "cache_native_shaping_v6"
        assert row["input_composition"]["decision"] == "cache_native_composition"


def _responses_request(items: list, session: str) -> dict:
    return {"model": "fixture",
            "instructions": f"You are a coding agent.\nSession folder: C:{BS}Users{BS}u{BS}.copilot{BS}session-state{BS}{session}\nBe brief.",
            "input": items, "tools": [{"type": "function", "name": name} for name in ("rg", "glob", "view")]}


def test_bridge_rewrite_keeps_history_prefix():
    """Cache.bridge_prefix_stable and Cache.cache_prefix_kept, on rewrite_request across a growing session. The
    fixture sends the same instructions and tools on every call; that the real client does is an assumption."""
    rng, count = random.Random(14), tokens.estimate
    items = [{"role": "user", "content": [{"type": "input_text", "text": "Find every caller of parse_header."}]}]
    previous, shaped = None, 0
    for step in range(8):
        name, arguments, output = rng.choice([
            ("rg", {"pattern": "parse_header"}, _search_output(rng) * 15),
            ("glob", {"pattern": "**/*.py"}, _path_list(rng) * 20),
            ("view", {"path": "big.py"}, _view_text(rng))])
        items = items + [{"type": "function_call", "call_id": f"call_{step}", "name": name, "arguments": json.dumps(arguments)},
                         {"type": "function_call_output", "call_id": f"call_{step}", "output": output}]
        request, stats = bridge.rewrite_request(_responses_request(items, "3f2a9c"), count)
        shaped += stats["shaped"]
        assert stats["stable_prefix"]
        if previous is not None:
            assert request["input"][:len(previous["input"])] == previous["input"]
            assert request["instructions"] == previous["instructions"] and request["tools"] == previous["tools"]
            assert json.dumps(request["input"]).startswith(json.dumps(previous["input"])[:-1])
        previous = request
    assert shaped > 0


def test_finding_bridge_fails_on_a_lone_surrogate():
    """Findings: Cache.bridge_prefix_stable takes shape as total; the pinned counter raises on a lone surrogate."""
    count = exact_counter()
    body = _responses_request([{"role": "user", "content": [{"type": "input_text", "text": "go"}]},
                               {"type": "function_call", "call_id": "a", "name": "rg", "arguments": "{}"},
                               {"type": "function_call_output", "call_id": "a", "output": "src/a.py:1:x\n" * 50 + chr(0xD800)}],
                              "3f2a9c")
    with pytest.raises(UnicodeEncodeError):
        bridge.rewrite_request(body, count)


def test_session_prefix_same_system_and_recoverable_folder():
    """SessionPrefix.system_same_across_sessions and SessionPrefix.folder_recoverable."""
    items = [{"role": "user", "content": [{"type": "input_text", "text": "Summarize the repository."}]}]
    first = native_transport.stable_session_prefix(_responses_request(items, "aaaa-1111"))
    second = native_transport.stable_session_prefix(_responses_request(items, "bbbb-2222"))
    assert first["instructions"] == second["instructions"]
    assert native_transport.SESSION_FOLDER_MOVED in first["instructions"]
    folder, _, rest = first["input"][0]["content"][0]["text"].partition("\n\n")
    assert folder == f"Session folder: C:{BS}Users{BS}u{BS}.copilot{BS}session-state{BS}aaaa-1111"
    assert rest == "Summarize the repository."


def _policy_request(rng: random.Random, tools: int) -> dict:
    messages = [{"role": "system", "content": "Stable system text."}, {"role": "user", "content": "Give an overview."}]
    for index in range(tools):
        messages += [{"role": "assistant", "content": None, "tool_calls": [
                         {"id": f"c{index}", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
                     {"role": "tool", "tool_call_id": f"c{index}", "content": f"result {index} " + "text " * rng.randint(5, 300),
                      "metadata": {"order": index}}]
    return {"model": "fixture", "messages": messages, "metadata": {"untouched": True}}


def test_plan_request_never_expands_and_keeps_protected_messages():
    """Policy.greedy_never_expands, Policy.greedy_strict, Policy.greedy_count_le, Policy.protected_unchanged and
    Policy.metadata_unchanged, on plan_request with policy v1. Some proposals are longer than the original, so
    the reject branch runs."""
    rng, rejected = random.Random(15), 0
    for _ in range(300):
        request = _policy_request(rng, rng.randint(1, 8))
        original = json.loads(json.dumps(request))
        stable = rng.randint(0, len(request["messages"]))
        exact = tuple(sorted(rng.sample(range(len(request["messages"])), rng.randint(0, 2))))
        saved = {}

        def transform(text, saved=saved):
            reference = f"ref:{len(saved)}"
            saved[reference] = text
            padding = "pad " * rng.choice((0, 0, 400))
            return TransformResult(f"overview; recover {reference} {padding}", reference)

        policy = RequestPolicy(enabled=True, min_tool_chars=1, max_transforms=rng.randint(1, 4),
                               keep_recent_tool_results=rng.randint(1, 3))
        plan = plan_request(request, policy=policy, protocol="chat-completions-v1", intent="overview",
                            transform=transform, recover=saved.__getitem__, count=len,
                            stable_prefix_messages=stable, exact_message_indices=exact)
        rejected += len(saved) > len(plan.changed_message_indices)
        assert request == original
        assert plan.tokens_after <= plan.tokens_before and plan.wire_bytes_after <= plan.wire_bytes_before
        if plan.status == "transformed":
            assert plan.tokens_after < plan.tokens_before
            assert plan.tokens_after == len(serialize_request(plan.request))
        assert len(plan.changed_message_indices) <= policy.max_transforms
        tool_indices = [i for i, m in enumerate(original["messages"]) if m["role"] == "tool"]
        newest = set(tool_indices[-policy.keep_recent_tool_results:])
        for index, (before, after) in enumerate(zip(original["messages"], plan.request["messages"], strict=True)):
            assert {k: v for k, v in before.items() if k != "content"} == {k: v for k, v in after.items() if k != "content"}
            if index < stable or index in exact or index in newest or before["role"] != "tool":
                assert after == before
        assert {k: v for k, v in plan.request.items() if k != "messages"} == {
            k: v for k, v in original.items() if k != "messages"}
    assert rejected > 20


def test_fit_matches_the_lean_model():
    """NavCap.fit_prefix and NavCap.fit_cost_le: _fit keeps the longest prefix whose cost fits the budget."""
    rng = random.Random(16)
    for _ in range(500):
        lines = ["word " * rng.randint(0, 30) for _ in range(rng.randint(0, 30))]
        budget = rng.randint(0, 300)
        shown, hidden = symbol_index._fit(lines, budget)
        model, left = [], budget
        for line in lines:
            cost = symbol_index._count(line) + 1
            if cost > left:
                break
            model.append(line)
            left -= cost
        assert shown == model and hidden == len(lines) - len(model)
        assert sum(symbol_index._count(line) + 1 for line in shown) <= budget


def _lean_assemble(header: list[str], entries: list[str], footer, budget: int) -> str:
    """NavCap.assemble: shrink from _fit's guess while the whole text does not fit, then cutN."""
    count = symbol_index._count
    shown = len(symbol_index._fit(entries, budget - count("\n".join(header)))[0])
    while shown > 0 and count("\n".join([*header, *entries[:shown], *footer(shown)])) > budget:
        shown -= 1
    text = "\n".join([*header, *entries[:shown], *footer(shown)])
    for _ in range(len(text) + 1):
        if count(text) <= budget:
            break
        text = text[:len(text) * 4 // 5]
    return text


def test_assemble_matches_the_lean_model():
    """NavCap.assemble_le, NavCap.shrink_le and NavCap.shrink_maximal: _assemble returns exactly the model's text,
    and it fits the budget, even when the header and footer alone do not."""
    rng = random.Random(20)
    for _ in range(400):
        header = ["header " * rng.randint(0, 40)]
        entries = ["entry " * rng.randint(0, 30) for _ in range(rng.randint(0, 40))]
        budget = rng.randint(0, 600)

        def footer(shown, total=len(entries)):
            return [f"[{total - shown} more not shown]"] if shown < total else []
        text = symbol_index._assemble(header, entries, footer, budget)
        assert text == _lean_assemble(header, entries, footer, budget)
        assert symbol_index._count(text) <= budget


def test_fallback_estimate_is_the_model(fallback_counter):
    """NavCap.est: without the vocabulary, tokens.estimate is ceil(characters / 4)."""
    rng = random.Random(17)
    for _ in range(2000):
        text = "".join(rng.choice("ab é雪\n") for _ in range(rng.randint(0, 80)))
        assert fallback_counter(text) == (len(text) + 3) // 4


def _nav_repo(root: Path) -> None:
    (root / "pkg").mkdir()
    functions = [f"def handler_{i}_with_a_rather_long_descriptive_name(argument_one, argument_two, third=None):\n"
                 f"    return target_function(argument_one) + {i}\n" for i in range(400)]
    (root / "pkg/big.py").write_text("def target_function(value):\n    return value\n\n\n" + "\n".join(functions),
                                     encoding="utf-8")
    for i in range(700):
        (root / f"d{i}").mkdir()
        (root / f"d{i}/util.py").write_text(f"def helper_{i}():\n    return {i}\n", encoding="utf-8")


@pytest.fixture(scope="module")
def nav_results(tmp_path_factory):
    root = tmp_path_factory.mktemp("nav")
    _nav_repo(root)
    index = symbol_index.SymbolIndex(root)
    try:
        return {"locate": index.locate("handler"), "outline": index.locate("pkg/big.py"),
                "not_one_file": index.locate("util.py"), "read": index.read("pkg/big.py"),
                "range": index.read("pkg/big.py:1-800"), "impact": index.impact("target_function")}
    finally:
        index.close()


def test_navigation_results_within_budget(nav_results):
    """NavCap.assemble_le, on every tool: each result, footer and newlines included, costs at most BUDGET. The
    not_one_file result cost 2,401 under cl100k before results were measured whole."""
    assert "files; use one:" in nav_results["not_one_file"] and "more]" in nav_results["not_one_file"]
    assert nav_results["impact"].count(chr(10)) > 50
    for name, text in nav_results.items():
        assert symbol_index._count(text) <= symbol_index.BUDGET, name


def test_uncut_read_within_budget(tmp_path, fallback_counter):
    """NavCap.uncut_overflow_attained is why _lines measures the whole text: across body sizes around the old
    overflow, read stays within BUDGET under the fallback estimate (it returned 2,401 at 9,584 characters)."""
    largest = 0
    for size in range(9576, 9592):
        folder = tmp_path / f"body{size}"
        folder.mkdir()
        lengths = [42] * 200
        for i in range(size - 892 - 199 - 8400):
            lengths[i] += 1
        (folder / "abcd.md").write_text("\n".join("x" * n for n in lengths), encoding="utf-8")
        index = symbol_index.SymbolIndex(folder)
        try:
            largest = max(largest, fallback_counter(index.read("abcd.md")))
        finally:
            index.close()
    assert largest <= symbol_index.BUDGET


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_cache_writes_never_cost_less_than_reads():
    """The hypothesis of Measurement.asRun_le_cold, on every recorded call that lists both prices. In the recorded
    studies those are the default-routing calls, which share one price pair."""
    files = sorted((REPO / "evidence").glob("*/**/calls.jsonl"))
    if not files:
        pytest.skip("no recorded calls")
    pairs = set()
    for path in files:
        for call in _read_jsonl(path):
            prices = tokenomics.prices_of(call.get("token_details_json"))
            if "cache_read" in prices and "cache_write" in prices:
                pairs.add((prices["cache_read"], prices["cache_write"]))
    assert pairs and all(write >= read for read, write in pairs)


def _chosen(suite: Path) -> dict:
    rows = {}
    for row in _read_jsonl(suite / "results.jsonl"):
        key = (row["task"], row["arm"])
        if key not in rows or (rows[key]["status"] == "infra" and row["session"].endswith("-rerun")):
            rows[key] = row
    return rows


def test_cold_repricing_matches_the_definition():
    """Measurement.cold and Measurement.cold_term_is_coldened_charge: each session's recorded cold cost is its as-run
    cost plus the first main-agent call's cache reads times the write-minus-read price."""
    checked = 0
    for suite in ("django-common", "django-rare"):
        for row in _chosen(STUDY / suite).values():
            calls = _read_jsonl(STUDY / suite / "runs" / row["session"] / "calls.jsonl")
            first = next(c for c in calls if not c.get("agent_id"))
            prices = tokenomics.prices_of(first["token_details_json"])
            term = (first.get("cache_read_tokens") or 0) * (prices["cache_write"] - prices["cache_read"])
            assert abs(row["usage"]["nano_cold"] - row["usage"]["nano"] - term) <= 1
            checked += 1
    assert checked == 30


def test_bootstrap_interval_within_task_range():
    """Measurement.resample_within_task_range: each reported CI lies between the smallest and largest task ratio,
    and the point estimate is the ratio of sums."""
    analysis = json.loads((STUDY / "analysis.json").read_text(encoding="utf-8"))["django_15_tasks"]
    rows = {**_chosen(STUDY / "django-common"), **_chosen(STUDY / "django-rare")}
    tasks = sorted({task for task, _ in rows})
    values = {"raw_tokens": lambda r: r["usage"]["input"] + r["usage"]["output"],
              "usd_cold": lambda r: r["usage"]["nano_cold"]}
    for name, value in values.items():
        ratios = [value(rows[(t, "tm")]) / value(rows[(t, "stock")]) - 1 for t in tasks]
        low, high = analysis[name]["ci95"]
        assert min(ratios) - 1e-4 <= low <= high <= max(ratios) + 1e-4, name
        total = sum(value(rows[(t, "tm")]) for t in tasks) / sum(value(rows[(t, "stock")]) for t in tasks) - 1
        assert abs(total - analysis[name]["change"]) <= 1e-4, name


def test_hero_verdicts_follow_the_rule():
    """Measurement.heroHolds as analyze.py applies it: a claim holds iff the CI's upper reduction reaches it."""
    check = json.loads((STUDY / "analysis.json").read_text(encoding="utf-8"))["django_15_tasks"]["hero_check"]
    for endpoint in ("raw_tokens", "usd_cold"):
        entry = check[endpoint]
        assert entry["holds"] == (entry["reduction_ci95"][1] >= entry["hero"])
