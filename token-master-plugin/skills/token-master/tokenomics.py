#!/usr/bin/env python
"""TokenMaster tokenomics: a ccusage-style report of Copilot CLI usage, cost and TokenMaster savings.

Data, read locally and never changed:
- <COPILOT_HOME>/session-store.db, table assistant_usage_events: Copilot CLI's own record of every model call, with
  GitHub's token counts and GitHub's charge for the call (total_nano_aiu; 1e9 nano = 1 AI credit = $0.01).
- <COPILOT_HOME>/token-master/launches.jsonl: written by the TokenMaster launcher when Copilot CLI starts and exits.
  A call counts as a TokenMaster call if its session's folder matches a launch, and the session's first call and the
  call itself fall within that launch's run.

Actual tokens and cost are measured. Savings are estimated (docs/TOKENOMICS.md). The estimate assumes that stock
Copilot CLI would have made the same model calls:
- Lean tool set: every main-agent call sent fewer fixed tokens than stock Copilot CLI ("lean"), less the navigation
  tools' definitions when they were installed ("nav"). These tokens are priced at the call's cache-read price.
- First call: stock Copilot CLI's first call sends the same prompt plus those fixed tokens, and reads only its usual
  cached prefix: the median first-call cache read of this store's own stock sessions with the same model, else the
  calibration's "stock_first_cached". It writes the rest to the prompt cache. The difference to the actual
  first-call write is priced at (cache-write price - cache-read price). It can be negative.
Not counted: model calls that graph navigation saved, v6 shaping, and any other change in model behavior. On the 10
measured A/B runs (Copilot CLI 1.0.98 and 1.0.78-3), the method gave 59% to 125% of the measured token saving.

  python tokenomics.py [daily|weekly|monthly|session] [--since YYYYMMDD] [--until YYYYMMDD] [--project TEXT]
                       [--only tokenmaster|stock] [--breakdown] [--order asc|desc] [--json] [--compact | --full]
                       [--ascii] [--no-color] [--copilot-home PATH]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import statistics
import sys
import tempfile

# Fixed prompt sizes depend on the Copilot CLI version. Per API: the tokens that the lean tool set removes from every
# call ("lean"), the tokens that the navigation tools add back ("nav"), and the tokens that stock Copilot CLI's first
# call reads from the prompt cache when another session of the same version ran shortly before ("stock_first_cached").
CALIBRATIONS = {
    # Probe of October 23, 2026 (evidence/copilot-version-probe-20261023); "nav" was measured on 1.0.78-3.
    "1.0.98": {"responses": {"model": "gpt-6-astra", "lean": 5558, "nav": 252, "stock_first_cached": 6450},
               "messages": {"model": "claude-opus-5.5", "lean": 9727, "nav": 531, "stock_first_cached": 11226}},
    # 45-task Django A/B of October 22, 2026 (evidence/django-scale-20261022): medians over its first calls.
    "1.0.78-3": {"responses": {"model": "gpt-6-astra", "lean": 6760, "nav": 252, "stock_first_cached": 0},
                 "messages": {"model": "claude-opus-5.5", "lean": 11540, "nav": 531, "stock_first_cached": 13393}},
}
CLI_VERSION = "1.0.98"  # the installed build that the launcher runs; other versions send other fixed prompts
CALIBRATION = CALIBRATIONS[CLI_VERSION]
CALIBRATION_SOURCE = "Copilot CLI 1.0.98, probe of October 23, 2026"
BENCHMARK = ("Measured on Copilot CLI 1.0.98 (PRS-6, 29 repo tasks + 15 Django tasks, Oct 26, 2026): full TokenMaster "
             "used 49.5%–58.5% (gpt-6-astra) and 38.0%–53.7% (claude-opus-5.5) fewer raw tokens than stock; on "
             "1.0.78-3 (45 Django tasks, Oct 22, 2026): 53.4% and 51.6% fewer.")
NANO_PER_USD = 1e11
LAUNCH_TIMEOUT = timedelta(hours=12)  # a launch without an end record counts as running for at most this long
REPORTS = ("daily", "weekly", "monthly", "session")


# ----------------------------------------------------------------------------------------------- data

def copilot_home(override: str | None = None) -> Path:
    return Path(override or os.environ.get("COPILOT_HOME") or Path.home() / ".copilot")


def parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def api_of(endpoint: str | None) -> str:
    endpoint = (endpoint or "").lower()
    if endpoint.endswith("/responses"):
        return "responses"
    if endpoint.endswith("/messages"):
        return "messages"
    return "other"


def prices_of(details: str | None) -> dict:
    """GitHub's price for each token type of one call, in nano-AIU per token."""
    try:
        rows = json.loads(details or "[]")
    except ValueError:
        return {}
    return {row["tokenType"]: row["costPerBatch"] / row["batchSize"]
            for row in rows if isinstance(row, dict) and row.get("batchSize") and "tokenType" in row}


def open_store(path: Path):
    """Read-only connection; if Copilot CLI holds the database, read a private copy instead."""
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        connection.execute("select count(*) from assistant_usage_events").fetchone()
        return connection, None
    except sqlite3.Error:
        folder = Path(tempfile.mkdtemp(prefix="tokenomics-"))
        for suffix in ("", "-wal", "-shm"):
            source = Path(f"{path}{suffix}")
            if source.exists():
                shutil.copy2(source, folder / f"{path.name}{suffix}")
        return sqlite3.connect(folder / path.name), folder


def load_store(path: Path) -> tuple[list[dict], dict]:
    connection, copy = open_store(path)
    try:
        columns = {row[1] for row in connection.execute("pragma table_info(assistant_usage_events)")}
        wanted = ["session_id", "created_at", "model", "api_endpoint", "input_tokens", "output_tokens",
                  "cache_read_tokens", "cache_write_tokens", "total_nano_aiu", "token_details_json", "agent_id"]
        select = ", ".join(name if name in columns else f"null as {name}" for name in wanted)
        calls = []
        for row in connection.execute(f"select {select} from assistant_usage_events order by created_at"):
            record = dict(zip(wanted, row))
            at = parse_time(record["created_at"])
            if at is None:
                continue
            calls.append({"session": record["session_id"], "at": at, "model": record["model"] or "unknown",
                          "api": api_of(record["api_endpoint"]), "input": record["input_tokens"] or 0,
                          "output": record["output_tokens"] or 0, "cache_read": record["cache_read_tokens"] or 0,
                          "cache_write": record["cache_write_tokens"] or 0, "nano": record["total_nano_aiu"] or 0,
                          "prices": prices_of(record["token_details_json"]), "main": not record["agent_id"]})
        sessions = {}
        session_columns = {row[1] for row in connection.execute("pragma table_info(sessions)")}
        if {"id", "cwd"} <= session_columns:
            extra = [c for c in ("repository", "created_at") if c in session_columns]
            for row in connection.execute(f"select id, cwd{''.join(', ' + c for c in extra)} from sessions"):
                record = dict(zip(["id", "cwd", *extra], row))
                sessions[record["id"]] = {"cwd": record["cwd"] or "", "repository": record.get("repository") or "",
                                          "created": parse_time(record.get("created_at"))}
        return calls, sessions
    finally:
        connection.close()
        if copy:
            shutil.rmtree(copy, ignore_errors=True)


def load_launches(path: Path) -> list[dict]:
    starts, ends = {}, {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("id"):
                (starts if record.get("event") == "start" else ends)[record["id"]] = record
    launches = []
    for launch_id, record in starts.items():
        start = parse_time(record.get("at"))
        if start is None:
            continue
        stamp = (ends.get(launch_id) or {}).get("at")
        end = parse_time(stamp)
        if end and "." not in stamp:
            end += timedelta(seconds=1)  # records before October 23, 2026 hold whole seconds; cover the last one
        end = end or start + LAUNCH_TIMEOUT
        launches.append({"id": launch_id, "start": start, "end": end, "cwd": norm(record.get("cwd")),
                         "lean": bool(record.get("lean")), "bridge": bool(record.get("bridge")),
                         "nav": bool(record.get("nav"))})
    return sorted(launches, key=lambda launch: launch["start"])


def norm(folder: str | None) -> str:
    return os.path.normcase(os.path.normpath(folder)) if folder else ""


# ----------------------------------------------------------------------------------------------- savings

def stock_first_cached(calls: list[dict]) -> dict:
    """Per model: the median tokens that this store's own stock sessions read from the cache on their first call."""
    firsts = {}
    for call in calls:  # time order
        if call["main"] and not call["launch"]:
            firsts.setdefault((call["session"], call["model"]), call["cache_read"])
    by_model = defaultdict(list)
    for (_, model), cache_read in firsts.items():
        by_model[model].append(cache_read)
    return {model: statistics.median(values) for model, values in by_model.items()}


def estimate(calls: list[dict], sessions: dict, launches: list[dict], calibrations: dict | None = None) -> None:
    """Tag TokenMaster calls and add their estimated savings, in place."""
    calibrations = calibrations or CALIBRATION
    first_seen, session_start = set(), {}
    for call in calls:  # calls arrive in time order
        session_start.setdefault(call["session"], call["at"])
    for call in calls:
        call.update(launch=None, saved_tokens=0, saved_nano=0.0, lean_nano=0.0, first_nano=0.0, estimated=False)
        folder = norm((sessions.get(call["session"]) or {}).get("cwd"))
        started = session_start[call["session"]]
        # The session must have started during the launch: a stock session that ran just before it, in the same
        # folder, stays stock. A resumed session counts as stock.
        matches = [launch for launch in launches if folder and launch["cwd"] == folder
                   and launch["start"] <= started <= launch["end"] and launch["start"] <= call["at"] <= launch["end"]]
        if matches:
            call["launch"] = matches[-1]
    observed = stock_first_cached(calls)
    for call in calls:
        launch = call["launch"]
        if not launch:
            continue
        calibration = calibrations.get(call["api"])
        read, write = call["prices"].get("cache_read"), call["prices"].get("cache_write")
        if not call["main"] or calibration is None or read is None:
            continue  # subagent calls and uncalibrated APIs get no estimate
        fixed = (calibration["lean"] if launch["lean"] else 0) - (calibration["nav"] if launch["nav"] else 0)
        call.update(saved_tokens=fixed, lean_nano=fixed * read, estimated=True)
        key = (call["session"], launch["id"])
        cached = call["cache_read"] + call["cache_write"]
        if key not in first_seen:
            first_seen.add(key)
            if write is not None and cached:
                # Stock's first call: the same prompt plus the fixed tokens, minus the prefix that stock usually reads
                # from the cache: measured from this store's stock sessions, else the calibration. It can be smaller
                # than the actual write, for example on a cold TokenMaster start.
                usual = observed.get(call["model"], calibration["stock_first_cached"])
                stock_write = cached + fixed - min(usual, cached + fixed)
                call["first_nano"] = (stock_write - call["cache_write"]) * (write - read)
        call["saved_nano"] = call["lean_nano"] + call["first_nano"]


# ----------------------------------------------------------------------------------------------- aggregation

def period_of(call: dict, report: str) -> str:
    local = call["at"].astimezone()
    if report == "monthly":
        return local.strftime("%Y-%m")
    if report == "weekly":
        return (local.date() - timedelta(days=local.weekday())).isoformat()
    return local.date().isoformat()


def blank() -> dict:
    return {"calls": 0, "input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "total": 0, "nano": 0,
            "saved_tokens": 0, "saved_nano": 0.0, "lean_nano": 0.0, "first_nano": 0.0, "models": set(),
            "sessions": set(), "tm_sessions": set(), "tm_calls": 0, "tm_total": 0, "tm_nano": 0}


def add(bucket: dict, call: dict) -> None:
    bucket["calls"] += 1
    bucket["input"] += max(0, call["input"] - call["cache_read"] - call["cache_write"])
    bucket["output"] += call["output"]
    bucket["cache_write"] += call["cache_write"]
    bucket["cache_read"] += call["cache_read"]
    bucket["total"] += call["input"] + call["output"]
    bucket["nano"] += call["nano"]
    bucket["models"].add(call["model"])
    bucket["sessions"].add(call["session"])
    if call["launch"]:
        bucket["tm_sessions"].add(call["session"])
        bucket["tm_calls"] += 1
        bucket["tm_total"] += call["input"] + call["output"]
        bucket["tm_nano"] += call["nano"]
    for key in ("saved_tokens", "saved_nano", "lean_nano", "first_nano"):
        bucket[key] += call[key]


def aggregate(calls: list[dict], report: str, breakdown: bool) -> tuple[list[tuple[str, dict, dict]], dict]:
    groups, per_model, total = defaultdict(blank), defaultdict(lambda: defaultdict(blank)), blank()
    for call in calls:
        key = call["session"] if report == "session" else period_of(call, report)
        add(groups[key], call)
        add(total, call)
        if breakdown:
            add(per_model[key][call["model"]], call)
    rows = [(key, groups[key], dict(per_model[key])) for key in groups]
    return rows, total


def plain(bucket: dict) -> dict:
    out = {key: (sorted(value) if isinstance(value, set) else value) for key, value in bucket.items()}
    for key in ("sessions", "tm_sessions"):
        out[key] = len(bucket[key])
    for key in ("nano", "saved_nano", "lean_nano", "first_nano", "tm_nano"):
        out[key.replace("nano", "usd")] = round(bucket[key] / NANO_PER_USD, 6)
        del out[key]
    out["saved_tokens_pct"] = pct(bucket["saved_tokens"], bucket["tm_total"] + bucket["saved_tokens"])
    out["saved_usd_pct"] = pct(bucket["saved_nano"], bucket["tm_nano"] + bucket["saved_nano"])
    return out


def pct(part: float, whole: float) -> float | None:
    return round(100 * part / whole, 1) if whole else None


# ----------------------------------------------------------------------------------------------- rendering

BOX = {"tl": "┌", "tm": "┬", "tr": "┐", "ml": "├", "mm": "┼", "mr": "┤", "bl": "└", "bm": "┴", "br": "┘",
       "h": "─", "v": "│"}
ASCII = {key: ("-" if key == "h" else "|" if key == "v" else "+") for key in BOX}
COLORS = {"head": "36", "total": "33", "saved": "32", "dim": "90", "title": "1"}


class Painter:
    def __init__(self, color: bool):
        self.color = color

    def __call__(self, text: str, style: str) -> str:
        return f"\033[{COLORS[style]}m{text}\033[0m" if self.color and text else text


def money(nano: float) -> str:
    return f"{'-' if nano < 0 else ''}${abs(nano) / NANO_PER_USD:,.2f}"


def table(headers: list[str], rows: list[list[str]], right: set[int], chars: dict, paint: Painter,
          styles: list[str | None]) -> str:
    cells = [[cell.split("\n") for cell in row] for row in [headers, *rows]]
    widths = [max(len(line) for row in cells for line in row[i]) for i in range(len(headers))]

    def rule(left, mid, end):
        return left + mid.join(chars["h"] * (w + 2) for w in widths) + end

    out = [rule(chars["tl"], chars["tm"], chars["tr"])]
    for index, row in enumerate(cells):
        style = "head" if index == 0 else styles[index - 1]
        for depth in range(max(len(cell) for cell in row)):
            parts = []
            for column, cell in enumerate(row):
                text = cell[depth] if depth < len(cell) else ""
                text = text.rjust(widths[column]) if column in right else text.ljust(widths[column])
                parts.append(" " + (paint(text, style) if style else text) + " ")
            out.append(chars["v"] + chars["v"].join(parts) + chars["v"])
        out.append(rule(chars["ml"], chars["mm"], chars["mr"]) if index < len(cells) - 1
                   else rule(chars["bl"], chars["bm"], chars["br"]))
    return "\n".join(out)


def banner(title: str, chars: dict, ascii_mode: bool, paint: Painter) -> str:
    width = len(title) + 6
    top, bottom = ("+", "+") if ascii_mode else ("╭", "╰")
    end_top, end_bottom = ("+", "+") if ascii_mode else ("╮", "╯")
    line = chars["h"] * width
    blank_line = chars["v"] + " " * width + chars["v"]
    return "\n".join([top + line + end_top, blank_line, chars["v"] + "   " + paint(title, "title") + "   " + chars["v"],
                      blank_line, bottom + line + end_bottom])


def mode_of(launch: dict | None) -> str:
    if not launch:
        return "-"
    parts = [name for name in ("lean", "nav", "bridge") if launch[name]]
    return "+".join(parts) or "launcher"


def render(report: str, rows: list, total: dict, args, sessions: dict, data_path: Path, launches: list,
           calls: list) -> str:
    ascii_mode = args.ascii
    chars = ASCII if ascii_mode else BOX
    paint = Painter(args.color)
    mark, bullet = ("~", "-") if ascii_mode else ("≈", "•")
    session_modes, session_start = {}, {}
    for call in calls:
        session_start.setdefault(call["session"], call["at"])
        if call["launch"]:
            session_modes.setdefault(call["session"], mode_of(call["launch"]))
    full = not args.compact
    first = "Session" if report == "session" else {"weekly": "Week of", "monthly": "Month"}.get(report, "Date")
    started_column = report == "session" and full
    headers = [first, "Models", *(["Started"] if started_column else []),
               *(["Calls", "Input", "Output", "Cache Write", "Cache Read"] if full else []),
               "Total Tokens", "Cost (USD)", "TokenMaster", f"Saved Tokens {mark}", f"Saved (USD) {mark}"]
    right = set(range(3 if started_column else 2, len(headers))) - {headers.index("TokenMaster")}
    body, styles = [], []

    def cells(name: str, bucket: dict, models: str, started: str, tm: str) -> list[str]:
        row = [name, models, *([started] if started_column else [])]
        if full:
            row += [f"{bucket['calls']:,}", f"{bucket['input']:,}", f"{bucket['output']:,}",
                    f"{bucket['cache_write']:,}", f"{bucket['cache_read']:,}"]
        saved_tokens, saved_cost = "-", "-"
        if bucket["tm_calls"]:
            stock_tokens, stock_nano = bucket["tm_total"] + bucket["saved_tokens"], bucket["tm_nano"] + bucket["saved_nano"]
            saved_tokens, saved_cost = f"{bucket['saved_tokens']:,}", money(bucket["saved_nano"])
            if full and stock_tokens:  # compact mode leaves the percentages to the savings panel
                saved_tokens += f" ({pct(bucket['saved_tokens'], stock_tokens)}%)"
            if full and stock_nano:
                saved_cost += f" ({pct(bucket['saved_nano'], stock_nano)}%)"
        return row + [f"{bucket['total']:,}", money(bucket["nano"]), tm, saved_tokens, saved_cost]

    for key, bucket, per_model in rows:
        if report == "session":
            info = sessions.get(key) or {}
            project = info.get("repository") or Path(info.get("cwd") or "?").name
            name, tm = f"{key[:8]}\n{project[:28 if full else 20]}", session_modes.get(key, "-")
            started = session_start[key].astimezone().strftime("%Y-%m-%d %H:%M") if key in session_start else ""
        else:
            name, started = key, ""
            tm = f"{len(bucket['tm_sessions'])}/{len(bucket['sessions'])} sessions"
        models = "\n".join(f"{bullet} {model}" for model in sorted(bucket["models"]))
        body.append(cells(name, bucket, models, started, tm))
        styles.append(None)
        for model, sub in sorted(per_model.items()):
            body.append(cells(f"  {'>' if ascii_mode else '└'} {model}", sub, "", "", ""))
            styles.append("dim")
    body.append(cells("Total", total, "", "", f"{len(total['tm_sessions'])}/{len(total['sessions'])} sessions"))
    styles.append("total")
    separator = " - " if ascii_mode else " · "
    title = separator.join(["TokenMaster Tokenomics", "Copilot CLI", report.capitalize()])
    out = [banner(title, chars, ascii_mode, paint), "", table(headers, body, right, chars, paint, styles), ""]
    out += savings_panel(total, paint, mark, calls)
    out.append(paint(f"Data: {data_path}{separator}{len(launches)} TokenMaster launches on record{separator}"
                     "times are local", "dim"))
    out.append(paint(f"Tip: in Copilot CLI, `! {shell_command(sys.executable, Path(__file__).resolve())[1]}` shows this "
                     "report without spending model tokens; /tokenomics asks the model to run it.", "dim"))
    return "\n".join(out)


def shell_command(python, script) -> tuple[str, str]:
    """Copilot CLI's shell tool and the command line that runs this report with UTF-8 output."""
    if sys.platform == "win32":
        return "powershell", f'[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); & "{python}" "{script}"'
    return "bash", f'"{python}" "{script}"'


def launcher_command() -> str:
    """Starts Copilot CLI through the launcher next to this script, with this Python: a bare `python` can be missing."""
    launcher = Path(__file__).resolve().with_name("brainspace_copilot_bridge.py")
    return f'{"& " if sys.platform == "win32" else ""}"{sys.executable}" "{launcher}" -- copilot'


def savings_panel(total: dict, paint: Painter, mark: str, calls: list) -> list[str]:
    lines = [paint("TokenMaster savings (estimated)", "title")]
    if not total["tm_calls"]:
        lines += ["  No TokenMaster calls in this range. Start Copilot CLI through the TokenMaster launcher:",
                  f"  {launcher_command()}", ""]
        return lines
    stock_tokens = total["tm_total"] + total["saved_tokens"]
    stock_nano = total["tm_nano"] + total["saved_nano"]
    uncalibrated = sum(1 for call in calls if call["launch"] and not call["estimated"])
    rows = [
        ("TokenMaster sessions", f"{len(total['tm_sessions'])} of {len(total['sessions'])}",
         f"{total['tm_calls']:,} model calls"),
        ("Tokens, actual", f"{total['tm_total']:,}", "GitHub's token counts"),
        (f"Tokens without TokenMaster {mark}", f"{stock_tokens:,}",
         paint(f"saved {total['saved_tokens']:,} ({pct(total['saved_tokens'], stock_tokens)}%)", "saved")),
        ("Cost, actual", money(total["tm_nano"]), "GitHub's own charge per call"),
        (f"Cost without TokenMaster {mark}", money(stock_nano),
         paint(f"saved {money(total['saved_nano'])} ({pct(total['saved_nano'], stock_nano)}%)", "saved")),
        ("  of which lean tool set", money(total["lean_nano"]),
         f"{total['saved_tokens']:,} fewer fixed tokens, priced as cache reads"),
        ("  of which first calls", money(total["first_nano"]), "prompt-cache writes on each session's first call"),
    ]
    width = max(len(row[0]) for row in rows)
    value_width = max(len(row[1]) for row in rows)
    lines += [f"  {name.ljust(width)}  {value.rjust(value_width)}  {note}" for name, value, note in rows]
    lines.append(paint("  The estimate assumes stock Copilot CLI would have made the same model calls. Not counted: "
                       "calls saved by graph navigation, v6 shaping, other behavior changes.", "dim"))
    if uncalibrated:
        lines.append(paint(f"  {uncalibrated} TokenMaster calls have no estimate (subagents or an API without "
                           "calibration).", "dim"))
    lines.append(paint(f"  Calibration: {CALIBRATION_SOURCE}; other Copilot CLI versions send other fixed prompts. On the "
                       "measured A/B runs (1.0.78-3), this method gave 72% to 125% of the measured token saving. "
                       "Method: docs/TOKENOMICS.md.", "dim"))
    lines.append(paint(f"  {BENCHMARK}", "dim"))
    lines.append("")
    return lines


# ----------------------------------------------------------------------------------------------- main

def in_range(call: dict, since: date | None, until: date | None) -> bool:
    day = call["at"].astimezone().date()
    return (since is None or day >= since) and (until is None or day <= until)


def day_arg(text: str) -> date:
    try:
        return datetime.strptime(text.replace("-", ""), "%Y%m%d").date()
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected YYYYMMDD, got {text!r}") from error


def build(args) -> dict:
    home = copilot_home(args.copilot_home)
    store = home / "session-store.db"
    if not store.is_file():
        raise SystemExit(f"No Copilot CLI session store at {store}. Run Copilot CLI first, or pass --copilot-home.")
    calls, sessions = load_store(store)
    launches = load_launches(home / "token-master" / "launches.jsonl")
    estimate(calls, sessions, launches)
    calls = [call for call in calls if in_range(call, args.since, args.until)]
    if args.project:
        needle = args.project.lower()
        calls = [call for call in calls
                 if needle in ((sessions.get(call["session"]) or {}).get("cwd", "") + " "
                               + (sessions.get(call["session"]) or {}).get("repository", "")).lower()]
    if args.only:
        calls = [call for call in calls if bool(call["launch"]) == (args.only == "tokenmaster")]
    rows, total = aggregate(calls, args.report, args.breakdown)
    if args.report == "session":
        start = {}
        for call in calls:
            start.setdefault(call["session"], call["at"])
        rows.sort(key=lambda row: start[row[0]], reverse=args.order == "desc")
    else:
        rows.sort(key=lambda row: row[0], reverse=args.order == "desc")
    return {"home": home, "store": store, "calls": calls, "sessions": sessions, "launches": launches,
            "rows": rows, "total": total}


def as_json(report: str, data: dict) -> dict:
    rows = []
    for key, bucket, per_model in data["rows"]:
        row = {"session" if report == "session" else "period": key, **plain(bucket)}
        if report == "session":
            info = data["sessions"].get(key) or {}
            row.update(cwd=info.get("cwd"), repository=info.get("repository"),
                       tokenmaster=next((mode_of(c["launch"]) for c in data["calls"]
                                         if c["session"] == key and c["launch"]), None))
        if per_model:
            row["breakdown"] = {model: plain(sub) for model, sub in sorted(per_model.items())}
        rows.append(row)
    return {"report": report, "source": str(data["store"]), "launches": len(data["launches"]), "rows": rows,
            "totals": plain(data["total"]), "estimate": {"cli_version": CLI_VERSION, "calibration": CALIBRATION,
                                                         "source": CALIBRATION_SOURCE,
                                                         "assumes": "stock Copilot CLI would have made the same calls",
                                                         "validation": "72% to 125% of the measured token saving, "
                                                                       "on Copilot CLI 1.0.78-3 A/B runs",
                                                         "not_counted": ["graph navigation's saved calls",
                                                                         "v6 shaping", "other behavior changes"]}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("report", nargs="?", default="daily", choices=REPORTS)
    parser.add_argument("--since", type=day_arg, help="first day to include, YYYYMMDD (local time)")
    parser.add_argument("--until", type=day_arg, help="last day to include, YYYYMMDD (local time)")
    parser.add_argument("--project", help="only sessions whose folder or repository contains this text")
    parser.add_argument("--only", choices=("tokenmaster", "stock"), help="only TokenMaster or only stock calls")
    parser.add_argument("--breakdown", action="store_true", help="one sub-row per model")
    parser.add_argument("--order", choices=("asc", "desc"), default="asc")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--compact", action="store_true", help="hide the input, output and cache columns")
    parser.add_argument("--full", action="store_true", help="never switch to compact mode on a narrow terminal")
    parser.add_argument("--ascii", action="store_true", help="draw tables with ASCII characters")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--copilot-home", help="Copilot CLI home (default: $COPILOT_HOME or ~/.copilot)")
    args = parser.parse_args(argv)
    if args.full:
        args.compact = False
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args.color = not args.no_color and not os.environ.get("NO_COLOR") and sys.stdout.isatty()
    data = build(args)
    if args.json:
        print(json.dumps(as_json(args.report, data), indent=2, default=str))
        return 0
    if not data["calls"]:
        print(f"No Copilot CLI usage in {data['store']} for the chosen range.")
        return 0
    text = render(args.report, data["rows"], data["total"], args, data["sessions"], data["store"],
                  data["launches"], data["calls"])
    width = shutil.get_terminal_size((0, 0)).columns if sys.stdout.isatty() else 0
    if width and not args.compact and not args.full and max(map(len, text.splitlines())) > width:
        args.compact = True  # like ccusage: a narrow terminal gets the compact table
        text = render(args.report, data["rows"], data["total"], args, data["sessions"], data["store"],
                      data["launches"], data["calls"])
        text += "\nCompact mode for this terminal width; widen it or pass --full for the cache columns."
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
