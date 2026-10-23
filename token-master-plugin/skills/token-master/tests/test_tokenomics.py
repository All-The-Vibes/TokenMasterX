"""tokenomics.py: a ccusage-style report from Copilot CLI's session store, with estimated TokenMaster savings."""
import importlib.util
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))
_spec = importlib.util.spec_from_file_location("tokenomics", SKILL / "tokenomics.py")
tokenomics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tokenomics)
_bridge_spec = importlib.util.spec_from_file_location("brainspace_copilot_bridge_t", SKILL / "brainspace_copilot_bridge.py")
bridge = importlib.util.module_from_spec(_bridge_spec)
_bridge_spec.loader.exec_module(bridge)

USD_PER_M = {"/responses": {"input": 10, "cache_read": 1, "cache_write": 12.5, "output": 50},
             "/v1/messages": {"input": 4, "cache_read": 0.2, "cache_write": 5, "output": 20}}
NANO_PER_TOKEN_PER_USD_PER_M = 1e5  # $1 per 1M tokens = 1e11 nano per 1M tokens = 1e5 nano per token


def call(session, at, endpoint, new, read, write, out, agent=None, model=None):
    prices = USD_PER_M[endpoint]
    nano = sum(count * prices[kind] * NANO_PER_TOKEN_PER_USD_PER_M
               for kind, count in (("input", new), ("cache_read", read), ("cache_write", write), ("output", out)))
    details = [{"batchSize": 1_000_000, "costPerBatch": int(prices[kind] * 1e11), "tokenCount": count,
                "tokenType": kind} for kind, count in (("input", new), ("cache_read", read),
                                                       ("cache_write", write), ("output", out))]
    model = model or ("gpt-6-astra" if endpoint == "/responses" else "claude-opus-5.5")
    return (session, agent, model, endpoint, new + read + write, out, read, write, int(nano), json.dumps(details), at)


SESSIONS = [("S", "C:/repo/a", "org/a", "2026-10-20T10:00:00Z"), ("T", "C:/repo/a", "org/a", "2026-10-20T11:00:00Z"),
            ("U", "C:/repo/b", "", "2026-10-21T09:00:00Z"), ("V", "C:/repo/b", "", "2026-10-21T12:00:00Z")]
CALLS = [call("S", "2026-10-20T10:00:05Z", "/responses", 4, 0, 13601, 40),            # stock, cold first call
         call("S", "2026-10-20T10:00:20Z", "/responses", 0, 13601, 1399, 50),
         call("T", "2026-10-20T11:00:05Z", "/responses", 2, 6921, 174, 30),           # TokenMaster, warm first call
         call("T", "2026-10-20T11:00:20Z", "/responses", 0, 7095, 2405, 40),
         call("T", "2026-10-20T11:00:30Z", "/responses", 0, 3000, 500, 20, agent="sub-1"),  # subagent: no estimate
         call("U", "2026-10-21T09:00:05Z", "/v1/messages", 0, 5000, 4331, 100),       # TokenMaster, lean only
         call("V", "2026-10-21T12:00:05Z", "/v1/messages", 0, 13393, 7474, 90)]       # stock
LAUNCHES = [{"event": "start", "id": "t", "at": "2026-10-20T10:59:00Z", "cwd": "C:/repo/a", "lean": True,
             "bridge": True, "nav": True},
            {"event": "end", "id": "t", "at": "2026-10-20T11:30:00Z"},
            {"event": "start", "id": "u", "at": "2026-10-21T08:59:00Z", "cwd": "C:/repo/b", "lean": True,
             "bridge": False, "nav": False},
            {"event": "end", "id": "u", "at": "2026-10-21T09:10:00Z"}]


def make_home(tmp_path, launches=LAUNCHES):
    home = tmp_path / "copilot-home"
    home.mkdir()
    db = sqlite3.connect(home / "session-store.db")
    db.execute("create table sessions (id text, cwd text, repository text, branch text, summary text, "
               "created_at text, updated_at text)")
    db.execute("create table assistant_usage_events (id integer primary key, session_id text, agent_id text, model "
               "text, api_endpoint text, input_tokens int, output_tokens int, cache_read_tokens int, "
               "cache_write_tokens int, total_nano_aiu int, token_details_json text, created_at text)")
    db.executemany("insert into sessions (id, cwd, repository, created_at) values (?, ?, ?, ?)", SESSIONS)
    db.executemany("insert into assistant_usage_events (session_id, agent_id, model, api_endpoint, input_tokens, "
                   "output_tokens, cache_read_tokens, cache_write_tokens, total_nano_aiu, token_details_json, "
                   "created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", CALLS)
    db.commit()
    db.close()
    if launches is not None:
        (home / "token-master").mkdir()
        (home / "token-master" / "launches.jsonl").write_text("".join(json.dumps(r) + "\n" for r in launches),
                                                             encoding="utf-8")
    return home


def estimated(home):
    calls, sessions = tokenomics.load_store(home / "session-store.db")
    tokenomics.estimate(calls, sessions, tokenomics.load_launches(home / "token-master" / "launches.jsonl"))
    return calls


def local_day(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone().date().isoformat()


def test_estimates_follow_the_documented_formula(tmp_path):
    calls = estimated(make_home(tmp_path))
    by = [(c["session"], c["saved_tokens"], round(c["lean_nano"]), round(c["first_nano"])) for c in calls]
    responses, messages = tokenomics.CALIBRATION["responses"], tokenomics.CALIBRATION["messages"]
    fixed = responses["lean"] - responses["nav"]  # lean tool set, less the navigation tools' definitions

    def first_call(calibration, fixed, read, write):  # stock writes its prompt plus the fixed tokens, less its cache
        return read + write + fixed - min(calibration["stock_first_cached"], read + write + fixed) - write

    assert by[0][1:] == by[1][1:] == (0, 0, 0)  # stock calls carry no estimate
    assert by[2] == ("T", fixed, round(fixed * 1e5), round(first_call(responses, fixed, 6921, 174) * 11.5e5))
    assert by[3] == ("T", fixed, round(fixed * 1e5), 0)  # only a session's first call gets the cache term
    assert by[4] == ("T", 0, 0, 0) and calls[4]["launch"] and not calls[4]["estimated"]  # subagent
    assert by[5] == ("U", messages["lean"], round(messages["lean"] * 0.2e5),
                     round(first_call(messages, messages["lean"], 5000, 4331) * 4.8e5))
    assert by[6][1:] == (0, 0, 0) and calls[6]["launch"] is None  # outside every launch window


def test_a_cold_tokenmaster_start_can_cost_more_than_a_warm_stock_start():
    responses = tokenomics.CALIBRATION["responses"]
    prices = {"input": 1e6, "cache_read": 1e5, "cache_write": 1.25e6, "output": 5e6}
    at = datetime(2026, 10, 23, 5, 32, tzinfo=timezone.utc)
    calls = [{"session": "W", "at": at, "model": "gpt-6-astra", "api": "responses", "input": 7317, "output": 110,
              "cache_read": 0, "cache_write": 7314, "nano": 0, "prices": prices, "main": True}]
    launch = {"id": "w", "start": at - timedelta(minutes=1), "end": at + timedelta(minutes=5),
              "cwd": tokenomics.norm("C:/w"), "lean": True, "bridge": True, "nav": False}
    tokenomics.estimate(calls, {"W": {"cwd": "C:/w"}}, [launch])
    stock_write = 7314 + responses["lean"] - responses["stock_first_cached"]
    assert calls[0]["first_nano"] == (stock_write - 7314) * 11.5e5 < 0
    assert tokenomics.money(-1.03e9) == "-$0.01"


def test_without_a_launch_registry_nothing_is_attributed(tmp_path):
    calls = estimated(make_home(tmp_path, launches=None))
    assert all(c["launch"] is None and c["saved_nano"] == 0 for c in calls)


def run_json(home, capsys, *args):
    assert tokenomics.main([*args, "--json", "--copilot-home", str(home)]) == 0
    return json.loads(capsys.readouterr().out)


def test_daily_json_totals_and_percentages(tmp_path, capsys):
    home = make_home(tmp_path)
    report = run_json(home, capsys, "daily")
    assert [row["period"] for row in report["rows"]] == sorted({local_day(c[-1]) for c in CALLS})
    totals = report["totals"]
    assert totals["calls"] == len(CALLS) and totals["sessions"] == 4 and totals["tm_sessions"] == 2
    assert totals["total"] == sum(c[4] + c[5] for c in CALLS)
    assert totals["usd"] == round(sum(c[8] for c in CALLS) / 1e11, 6)
    fixed = tokenomics.CALIBRATION["responses"]["lean"] - tokenomics.CALIBRATION["responses"]["nav"]
    assert totals["saved_tokens"] == 2 * fixed + tokenomics.CALIBRATION["messages"]["lean"]
    stock_like = totals["tm_total"] + totals["saved_tokens"]
    assert totals["saved_tokens_pct"] == round(100 * totals["saved_tokens"] / stock_like, 1)


def test_session_report_filters_and_modes(tmp_path, capsys):
    home = make_home(tmp_path)
    rows = run_json(home, capsys, "session", "--only", "tokenmaster")["rows"]
    assert [(row["session"], row["tokenmaster"]) for row in rows] == [("T", "lean+nav+bridge"), ("U", "lean")]
    assert [row["session"] for row in run_json(home, capsys, "session", "--only", "stock")["rows"]] == ["S", "V"]
    assert [row["session"] for row in run_json(home, capsys, "session", "--project", "repo/b")["rows"]] == ["U", "V"]
    day = local_day("2026-10-21T09:00:05Z").replace("-", "")
    assert {row["session"] for row in run_json(home, capsys, "session", "--since", day)["rows"]} == {"U", "V"}
    monthly = run_json(home, capsys, "monthly", "--breakdown")["rows"]
    assert len(monthly) == 1 and set(monthly[0]["breakdown"]) == {"gpt-6-astra", "claude-opus-5.5"}


def test_tables_render_in_box_and_ascii(tmp_path, capsys):
    home = make_home(tmp_path)
    for report in tokenomics.REPORTS:
        assert tokenomics.main([report, "--copilot-home", str(home)]) == 0
        out = capsys.readouterr().out
        assert "TokenMaster Tokenomics" in out and "Total" in out and "┌" in out and "savings" in out
    assert tokenomics.main(["daily", "--ascii", "--compact", "--copilot-home", str(home)]) == 0
    out = capsys.readouterr().out
    assert "+--" in out and "┌" not in out and "Cache Read" not in out


def test_a_stock_session_just_before_a_launch_stays_stock(tmp_path):
    # The real store of October 23: the stock session's last call came 66 ms after the launch's start second, and the
    # launcher recorded whole seconds, so its end second also held the TokenMaster session's last call.
    def at(seconds):
        return datetime(2026, 10, 23, 6, 10, tzinfo=timezone.utc) + timedelta(seconds=seconds)

    prices = {"input": 1e6, "cache_read": 1e5, "cache_write": 1.25e6, "output": 5e6}
    calls = [{"session": session, "at": at(seconds), "model": "gpt-6-astra", "api": "responses", "input": 5000,
              "output": 10, "cache_read": 4000, "cache_write": 990, "nano": 0, "prices": prices, "main": True}
             for session, seconds in (("stock", 43.084), ("stock", 45.066), ("tm", 49.252), ("tm", 51.271),
                                      ("tm", 53.176))]
    registry = tmp_path / "launches.jsonl"
    registry.write_text(json.dumps({"event": "start", "id": "l", "at": "2026-10-23T06:10:45Z", "cwd": "C:/repo",
                                    "lean": True, "bridge": True, "nav": False}) + "\n"
                        + json.dumps({"event": "end", "id": "l", "at": "2026-10-23T06:10:53Z"}) + "\n",
                        encoding="utf-8")
    tokenomics.estimate(calls, {"stock": {"cwd": "C:/repo"}, "tm": {"cwd": "C:/repo"}},
                        tokenomics.load_launches(registry))
    assert [bool(call["launch"]) for call in calls] == [False, False, True, True, True]


def test_launcher_records_copilot_launches_without_prompt_text(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    (tmp_path / "mcp-config.json").write_text('{"mcpServers": {"tokenmaster-nav": {}}}', encoding="utf-8")
    monkeypatch.setattr(bridge, "run_child", lambda parser, command, env: 3)
    assert bridge.run_recorded(None, ["copilot", "-p", "secret prompt"], {}, lean=True, bridge=False) == 3
    assert bridge.run_recorded(None, ["python", "-c", "pass"], {}, lean=False, bridge=False) == 3  # not Copilot
    records = [json.loads(line) for line in (tmp_path / "token-master" / "launches.jsonl").read_text().splitlines()]
    assert [r["event"] for r in records] == ["start", "end"] and records[0]["id"] == records[1]["id"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", records[0]["at"])  # milliseconds, UTC
    assert records[0]["lean"] is True and records[0]["bridge"] is False and records[0]["nav"] is True
    assert "secret" not in json.dumps(records)
    assert tokenomics.load_launches(tmp_path / "token-master" / "launches.jsonl")[0]["lean"] is True


def test_launch_without_an_end_record_counts_for_a_bounded_time(tmp_path):
    launches = [r for r in LAUNCHES if not (r["id"] == "t" and r["event"] == "end")]
    calls = estimated(make_home(tmp_path, launches=launches))
    assert calls[2]["launch"]["id"] == "t"
    loaded = {l["id"]: l for l in tokenomics.load_launches(tmp_path / "copilot-home" / "token-master" / "launches.jsonl")}
    assert loaded["t"]["end"] - loaded["t"]["start"] == tokenomics.LAUNCH_TIMEOUT
    assert datetime(2026, 10, 20, 11, 0, 5, tzinfo=timezone.utc) <= loaded["t"]["end"]
