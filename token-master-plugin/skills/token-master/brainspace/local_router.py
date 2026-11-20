"""R2: Zero-network integer-linear local router, pragmatic deixis & warm-cache Bayes thresholds.

Provides three composable components for ``brainspace_copilot_bridge.py``:
  1. ``r2_local_scores(prompt)``: deterministic pure-stdlib 2-scale (global + clause-max)
     sparse ``int16`` linear classifier distilled from Microsoft-Decision-1 (~0.1–2.5 ms CPU,
     zero network calls, <25 KB compressed weights).
  2. ``apply_discourse_deixis(scores, prompt, is_resumed=...)``: pragmatic log-odds update
     separating intra-session transcript back-references ("in Turn 1", "what you just recorded")
     from cross-session memory queries ("in yesterday's session", "older chat") on resumed turns.
  3. ``session_cache_state(...)`` & ``bayes_escalation_threshold(...)``: 2-stage warm-cache
     risk reader over ``<COPILOT_HOME>/session-store.db`` (``assistant_usage_events``) and
     Bayes-optimal family-specific escalation thresholds ``tau_f*(L_at_risk, w_f)``.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import sqlite3
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

FAMILIES: tuple[str, ...] = (
    "session_history",
    "agents",
    "skills",
    "sql",
    "background_shell",
    "copilot_docs",
    "workflows",
)

# Exact per-family schema token weights summed from tokenomics.LEAN_WEIGHTS (cl100k_base).
FAMILY_SCHEMA_TOKENS: dict[str, int] = {
    "session_history": 1619,
    "agents": 2674,
    "skills": 438,
    "sql": 674,
    "background_shell": 429,
    "copilot_docs": 189,
    "workflows": 2038,
}

# Quantized integer scoring constants (must match distillation specification).
SCALE = 256
NORM_SCALE = 64
GLOBAL_NUM = 9
CLAUSE_NUM = 16
POOL_DEN = 25
WINDOW_TOKENS = 20
WINDOW_STRIDE = 10

# 2-stage warm-cache Bayes threshold constants (Copilot CLI 1.0.112 empirically calibrated).
STATIC_LEAN_PREFIX = 3649       # static prefix preserved across Launch 2 <session_context> injection
CACHE_WARM_WINDOW = timedelta(minutes=5)
DEFAULT_WRITE_PREMIUM = 1.15    # (cache_write - cache_read) / input = (1.25 - 0.10) / 1.00
DEFAULT_MISS_COST = 6500.0      # single-turn missing-capability cost in uncached input token equivalents
LOCK_IN_READ_FACTOR = 0.40      # expected remaining calls * cache_read_ratio (4.0 * 0.10)
INTRA_SESSION_LOGIT_SHIFT = -6.0
CROSS_SESSION_LOGIT_SHIFT = 3.0

_TOKEN_RE = re.compile(r"`[^`\n]{1,64}`|[A-Za-z0-9_+#./\\-]+|\?")
_CAMEL_RE = re.compile(r"\b[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b")
_WORD_RE = re.compile(r"[a-z0-9_+#./-]+")

_STOPWORDS = frozenset({
    "a", "an", "the", "this", "that", "these", "those", "it", "its", "of", "to", "for",
    "with", "and", "or", "but", "so", "if", "as", "is", "are", "was", "were", "be",
    "been", "do", "does", "can", "could", "would", "should", "me", "my", "our",
    "we", "you", "your", "i", "at", "by", "on", "in", "into", "from", "about",
    "what", "which", "where", "how", "why", "who", "when", "there", "only", "any",
})
_KEEP_CONTENT = frozenset({
    "keep", "leave", "turn", "off", "up", "out", "over", "last", "past",
    "other", "another", "second", "back", "pass", "take",
})
_WEEKDAYS = frozenset({"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"})
_PAST_WORDS = frozenset({"yesterday", "older", "earlier", "previous", "prior", "past", "last", "ago"})
_DISCOURSE_STEMS = frozenset({"session", "chat", "conversation", "history", "discuss", "conclud", "decid", "ask"})
_WORKER_STEMS = frozenset({
    "agent", "subagent", "worker", "helper", "reviewer", "delegate",
    "spawn", "parallel", "concurrently", "simultaneously",
})
_BG_STEMS = frozenset({
    "background", "async", "asynchronously", "daemon", "watcher", "alive",
    "ephemeral", "listen", "listener", "poll", "shut", "terminate",
})
_SQL_STEMS = frozenset({
    "sqlite", "sql", "table", "row", "insert", "select", "group",
    "aggregate", "todo", "scratch", "database", "db",
})
_CLI_META_STEMS = frozenset({
    "copilot", "cli", "command", "flag", "hook", "keybinding",
    "setting", "banner", "slash", "mcp",
})
_KNOWN_TOOLS = frozenset({
    "session_store_sql", "todo_deps", "read_agent", "write_agent", "list_agents",
    "read_powershell", "stop_powershell", "list_powershell",
    "fetch_copilot_cli_documentation", "run_dynamic_workflow", "dynamic_workflows_manage",
})
_CODE_EXTS = frozenset({
    "py", "pyi", "js", "jsx", "ts", "tsx", "cs", "go", "rs", "php", "rb", "java",
    "c", "cpp", "h", "hpp", "swift", "kt", "yml", "yaml", "toml", "css", "scss", "html",
})
_DATA_EXTS = frozenset({"csv", "tsv", "sqlite", "db"})

# Pragmatic deixis patterns for cross-session vs intra-session discourse.
_CROSS_SESSION_DEIXIS = re.compile(
    r"(?<!')(?<!\")(?:"
    r"\b(?:previous|prior|past|earlier|other|older|another|last)\s+(?:copilot\s+)?(?:sessions?|chats?|conversations?|runs?|threads?)\b"
    r"|\b(?:across|between)\s+(?:my\s+|our\s+|all\s+)?(?:sessions?|chats?|conversations?)\b"
    r"|\b(?:query|search|check|inspect|scan|look\s+(?:up|in|through)|find\s+in|in|from|via|using|with)\s+`?session_store_sql\b`?(?!\s*['\"])"
    r"|\b(?:search|query|check|look\s+(?:up|in|through)|in|from)\s+(?:my\s+|our\s+)?session\s+history\b"
    r"|\b(?:yesterday(?:'s)?|last\s+(?:week|month|night)|(?:\d+|two|three|few|several)\s+(?:days?|weeks?)\s+ago)\b"
    r"|\b(?:earlier\s+this\s+week|before\s+today|last\s+time\s+(?:we|i|you))\b"
    r"|\b(?:on\s+|from\s+|in\s+|last\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:'s)?\b"
    r")",
    re.IGNORECASE,
)

_INTRA_SESSION_DEIXIS = re.compile(
    r"\b(?:"
    r"(?:turn|step|phase|part|stage)s?\s*#?\d+(?:\s*(?:and|&|,|to|-|through)\s*(?:(?:turn|step|phase|part|stage)s?\s*)?#?\d+)*"
    r"|(?:first|second|third|previous|prior|last|earlier)\s+(?:turn|step|prompt|reply|response|answer|message|output|check)"
    r"|earlier\s+(?:in\s+this\s+(?:session|chat|conversation|run|thread)|above)"
    r"|in\s+this\s+(?:session|chat|conversation|thread)"
    r"|(?:what|which|values?|numbers?|counts?|findings?|results?|items?)\s+(?:you|we)\s+(?:just\s+)?(?:recorded|found|computed|measured|read|ran|wrote|listed|identified|noted|collected|reported|discovered|observed|saw)"
    r"|(?:you|we)\s+just\s+(?:recorded|found|computed|measured|read|ran|wrote|listed|identified|noted|collected|reported|checked)"
    r"|(?:above|prior)\s+(?:findings?|results?|numbers?|measurements?|counts?|outputs?|summaries|summary)"
    r")\b",
    re.IGNORECASE,
)

_COMPILED_INDEX: tuple[list[int], dict[str, tuple[tuple[int, int], ...]]] | None = None


@dataclass(frozen=True)
class CacheState:
    """Observed warm prompt-cache state of a resumed Copilot CLI session."""
    launch_num: int = 1
    warm_cached_tokens: int = 0
    at_risk_tokens: int = 0
    write_premium: float = DEFAULT_WRITE_PREMIUM


def _stem_word(w: str) -> str:
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ing") and len(w) > 5:
        base = w[:-3]
        if len(base) >= 3 and base[-1] == base[-2]:
            base = base[:-1]
        return base
    if w.endswith("ed") and len(w) > 4:
        return w[:-2]
    if w.endswith("es") and len(w) > 4 and w[-3] in "sxzho":
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _per_token_info(raw_tok: str) -> tuple[set[str], list[tuple[str, str]]]:
    tfeats: set[str] = set()
    word_stems: list[tuple[str, str]] = []
    if raw_tok == "?":
        tfeats.add("punct:qmark")
        return tfeats, word_stems

    in_backtick = raw_tok.startswith("`") and raw_tok.endswith("`")
    inner = raw_tok[1:-1] if in_backtick else raw_tok
    if in_backtick:
        tfeats.add("shape:backtick")
    if _CAMEL_RE.search(inner):
        tfeats.add("shape:camel")

    has_path_sep = ("/" in inner or "\\" in inner)
    if has_path_sep:
        tfeats.add("shape:filepath")

    for tok in _WORD_RE.findall(inner.lower()):
        if tok.startswith("--") and len(tok) > 2:
            clean_flag = tok.lstrip("-").strip(".,")
            if clean_flag:
                tfeats.add("shape:cli_flag")
                tfeats.add(f"flag:{clean_flag}")
                word_stems.append((clean_flag, _stem_word(clean_flag)))
            continue
        if tok.startswith("/") and len(tok) > 1 and tok.count("/") == 1 and "." not in tok:
            tfeats.add("shape:slash_tok")
        is_code_tok = False
        if "." in tok:
            parts = [p for p in tok.split(".") if p]
            if len(parts) >= 2:
                ext = parts[-1]
                if ext in _CODE_EXTS:
                    is_code_tok = True
                    tfeats.add("shape:code_file")
                    tfeats.add(f"ext:{ext}")
                elif ext in _DATA_EXTS:
                    tfeats.add("shape:data_file")
                    tfeats.add(f"ext:{ext}")
                elif ext == "md":
                    tfeats.add("ext:md")
        if "_" in tok and not tok.startswith("_"):
            tfeats.add("shape:snake_ident")
            if tok in _KNOWN_TOOLS:
                tfeats.add(f"tool:{tok}")
        if "-" in tok and not tok.startswith("-") and not is_code_tok and not has_path_sep:
            hparts = [p for p in tok.split("-") if p]
            if len(hparts) >= 2 and all(p.isalpha() for p in hparts):
                tfeats.add("shape:hyphen_slug")

        if has_path_sep or is_code_tok:
            base_name = re.split(r"[/\\]", tok)[-1].split(".")[0]
            for sub in (p for p in re.split(r"[_-]+", base_name) if p):
                tfeats.add(f"codew:{sub}")
            continue

        for sub in (p for p in re.split(r"[/._+-]+", tok) if p):
            st = _stem_word(sub)
            word_stems.append((sub, st))
            tfeats.add(f"w:{sub}")
            tfeats.add(f"st:{st}")
            if sub in _WEEKDAYS:
                tfeats.add("sem:weekday")
            if sub in _PAST_WORDS:
                tfeats.add("sem:past_time")
            if st in _DISCOURSE_STEMS:
                tfeats.add("sem:discourse_mem")
            if st in _WORKER_STEMS:
                tfeats.add("sem:multi_worker")
            if st in _BG_STEMS:
                tfeats.add("sem:bg_proc")
            if st in _SQL_STEMS:
                tfeats.add("sem:tabular_sql")
            if st in _CLI_META_STEMS:
                tfeats.add("sem:cli_meta")
            if sub not in _STOPWORDS and len(sub) >= 4 and sub.isalpha():
                padded = f"<{sub[:14]}>"
                for i in range(len(padded) - 3):
                    tfeats.add(f"c:{padded[i:i+4]}")

    return tfeats, word_stems


def _span_features(token_infos: list[tuple[set[str], list[tuple[str, str]]]]) -> set[str]:
    feats: set[str] = set()
    stems: list[str] = []
    content: list[str] = []
    for tfeats, w_stems in token_infos:
        feats.update(tfeats)
        for w, st in w_stems:
            stems.append(st)
            if w not in _STOPWORDS or w in _KEEP_CONTENT:
                content.append(st)
    for i in range(len(stems) - 1):
        feats.add(f"b:{stems[i]} {stems[i+1]}")
    for i in range(len(content) - 1):
        feats.add(f"cb:{content[i]}~{content[i+1]}")
    for i in range(len(content) - 2):
        feats.add(f"cs:{content[i]}~{content[i+2]}")
    return feats


def _extract_two_scale(prompt: str) -> tuple[set[str], list[set[str]]]:
    raw_tokens = _TOKEN_RE.findall(prompt)
    if not raw_tokens:
        return set(), [set()]
    infos = [_per_token_info(tok) for tok in raw_tokens]
    global_feats = _span_features(infos)
    if len(infos) <= WINDOW_TOKENS:
        return global_feats, [global_feats]
    windows: list[set[str]] = []
    for start in range(0, len(infos), WINDOW_STRIDE):
        chunk = infos[start:start + WINDOW_TOKENS]
        if not chunk:
            break
        windows.append(_span_features(chunk))
        if start + WINDOW_TOKENS >= len(infos):
            break
    return global_feats, windows


def _norm_div(n_feats: int) -> int:
    return max(NORM_SCALE, int(round(math.sqrt(max(1, n_feats)) * NORM_SCALE)))


def _sigmoid(x: float) -> float:
    if x >= 35.0:
        return 1.0
    if x <= -35.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _logit(p: float) -> float:
    clamped = min(1.0 - 1e-12, max(1e-12, p))
    return math.log(clamped / (1.0 - clamped))


def _load_compiled_index() -> tuple[list[int], dict[str, tuple[tuple[int, int], ...]]]:
    global _COMPILED_INDEX
    if _COMPILED_INDEX is not None:
        return _COMPILED_INDEX
    from brainspace.local_router_weights import WEIGHTS_B85
    payload = json.loads(zlib.decompress(base64.b85decode(WEIGHTS_B85)).decode("utf-8"))
    biases = [int(payload[fam]["bias"]) for fam in FAMILIES]
    inv: dict[str, list[tuple[int, int]]] = {}
    for idx, fam in enumerate(FAMILIES):
        for feat, val in payload[fam]["weights"].items():
            inv.setdefault(feat, []).append((idx, int(val)))
    _COMPILED_INDEX = (biases, {k: tuple(v) for k, v in inv.items()})
    return _COMPILED_INDEX


def r2_local_scores(prompt: str) -> dict[str, float]:
    """Return zero-network calibrated [0, 1] capability probabilities for all 7 families."""
    if not prompt or not prompt.strip():
        return {}
    biases, inv = _load_compiled_index()
    g_feats, win_list = _extract_two_scale(prompt)
    if not g_feats:
        return {}
    n_fam = len(FAMILIES)
    g_ndiv = _norm_div(len(g_feats))
    g_dots = [0] * n_fam
    for f in g_feats:
        postings = inv.get(f)
        if postings is not None:
            for idx, val in postings:
                g_dots[idx] += val

    if len(win_list) == 1 and win_list[0] is g_feats:
        scores = {
            FAMILIES[i]: _sigmoid((biases[i] + (g_dots[i] * NORM_SCALE) // g_ndiv) / SCALE)
            for i in range(n_fam)
        }
    else:
        best_w = [-10**9] * n_fam
        for wf in win_list:
            w_ndiv = _norm_div(len(wf))
            w_dots = [0] * n_fam
            for f in wf:
                postings = inv.get(f)
                if postings is not None:
                    for idx, val in postings:
                        w_dots[idx] += val
            for i in range(n_fam):
                term = (CLAUSE_NUM * w_dots[i] * NORM_SCALE) // (POOL_DEN * w_ndiv)
                if term > best_w[i]:
                    best_w[i] = term

        scores = {
            FAMILIES[i]: _sigmoid(
                (biases[i] + (GLOBAL_NUM * g_dots[i] * NORM_SCALE) // (POOL_DEN * g_ndiv) + best_w[i]) / SCALE
            )
            for i in range(n_fam)
        }

    if has_cross_session_deixis(prompt):
        scores["session_history"] = _sigmoid(_logit(scores["session_history"]) + CROSS_SESSION_LOGIT_SHIFT)
    return scores


def has_cross_session_deixis(prompt: str) -> bool:
    """True when ``prompt`` explicitly refers to past sessions, chats, or prior calendar days."""
    return bool(prompt and _CROSS_SESSION_DEIXIS.search(prompt))


def is_intra_session_deixis(prompt: str) -> bool:
    """True when ``prompt`` refers to prior turns/steps/outputs of the active session without cross-session markers."""
    if not prompt:
        return False
    return bool(_INTRA_SESSION_DEIXIS.search(prompt)) and not bool(_CROSS_SESSION_DEIXIS.search(prompt))


def apply_discourse_deixis(
    scores: dict[str, float],
    prompt: str,
    *,
    is_resumed: bool,
    logit_shift: float = INTRA_SESSION_LOGIT_SHIFT,
) -> dict[str, float]:
    """Condition ``session_history`` posterior on resumed-session pragmatic deixis.

    On a resumed session (``is_resumed=True``), prior turns of the current session are already in
    the active context window. When the prompt exhibits intra-session anaphora ("in Turn 1",
    "what you recorded in Turn 1 and Turn 2") and no cross-session history marker ("yesterday",
    "previous session"), ``session_history`` log-odds are shifted by ``logit_shift`` (-6.0 nats),
    leaving all other 6 capability families untouched.
    """
    if not scores:
        return {}
    out = dict(scores)
    if not is_resumed or "session_history" not in out:
        return out
    raw = out.get("session_history")
    if type(raw) not in (int, float) or not math.isfinite(raw) or not 0.0 <= raw <= 1.0:
        return out
    if is_intra_session_deixis(prompt):
        out["session_history"] = _sigmoid(_logit(float(raw)) + logit_shift)
    return out


def _parse_iso(text: str | None) -> datetime | None:
    if not text or not isinstance(text, str):
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _extract_write_premium(details_json: str | None) -> float:
    if not details_json:
        return DEFAULT_WRITE_PREMIUM
    try:
        rows = json.loads(details_json)
    except ValueError:
        return DEFAULT_WRITE_PREMIUM
    if not isinstance(rows, list):
        return DEFAULT_WRITE_PREMIUM
    prices: dict[str, float] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("batchSize") and "tokenType" in row and "costPerBatch" in row:
            try:
                prices[str(row["tokenType"])] = float(row["costPerBatch"]) / float(row["batchSize"])
            except (TypeError, ValueError, ZeroDivisionError):
                continue
    inp = prices.get("input")
    read = prices.get("cache_read")
    write = prices.get("cache_write")
    if inp and inp > 0 and read is not None and write is not None and write >= read >= 0:
        premium = (write - read) / inp
        if math.isfinite(premium) and 0.0 <= premium <= 5.0:
            return premium
    return DEFAULT_WRITE_PREMIUM


def session_cache_state(
    session: str | None,
    *,
    copilot_home: Path | None = None,
    prior_launches: int = 1,
    now: datetime | None = None,
) -> CacheState:
    """Read ``session``'s warm cached prefix and 2-stage rewrite risk from ``session-store.db``.

    Matches ``tokenomics.py``'s 2-stage Copilot CLI 1.0.112 resume boundary:
      - Launch 2 (first resume): Copilot CLI injects ``<session_context>`` after the static
        tool + system-instruction prefix, so at most ``STATIC_LEAN_PREFIX`` tokens are at risk.
      - Launch 3+ (subsequent warm resume): ``<session_context>`` is already inside the cached
        prefix, so mutating ``--excluded-tools`` invalidates the full ``warm_cached_tokens`` prefix.
      - Calls older than ``CACHE_WARM_WINDOW`` (5 minutes) have expired caches (0 tokens at risk).
    """
    next_launch = max(2, int(prior_launches) + 1) if session else 1
    if not session:
        return CacheState(launch_num=1)
    home = copilot_home or Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot")
    db_path = home / "session-store.db"
    if not db_path.is_file():
        return CacheState(launch_num=next_launch)
    ref_now = now or datetime.now(timezone.utc)
    try:
        conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=1.0)
        try:
            cols = {row[1] for row in conn.execute("pragma table_info(assistant_usage_events)")}
            if not {"session_id", "created_at"} <= cols:
                return CacheState(launch_num=next_launch)
            wanted = [
                c if c in cols else f"null as {c}"
                for c in ("created_at", "cache_read_tokens", "cache_write_tokens", "token_details_json", "agent_id")
            ]
            rows = conn.execute(
                f"select {', '.join(wanted)} from assistant_usage_events "
                "where session_id = ? order by created_at desc limit 12",
                (session,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return CacheState(launch_num=next_launch)

    for created_at, cache_read, cache_write, details_json, agent_id in rows:
        if agent_id:  # subagent call; inspect main-agent prefix only
            continue
        call_at = _parse_iso(created_at)
        if call_at is None:
            continue
        age = ref_now - call_at
        if age < timedelta(seconds=-5) or age > CACHE_WARM_WINDOW:
            return CacheState(launch_num=next_launch)
        warm = max(0, int(cache_read or 0) + int(cache_write or 0))
        if warm <= 0:
            return CacheState(launch_num=next_launch)
        premium = _extract_write_premium(details_json)
        at_risk = min(warm, STATIC_LEAN_PREFIX) if next_launch <= 2 else warm
        return CacheState(
            launch_num=next_launch,
            warm_cached_tokens=warm,
            at_risk_tokens=at_risk,
            write_premium=premium,
        )
    return CacheState(launch_num=next_launch)


def _miss_cost() -> float:
    raw = os.environ.get("TOKENMASTER_ESCALATE_MISS_COST", "").strip()
    if raw:
        try:
            val = float(raw)
            if math.isfinite(val) and val > 0.0:
                return val
        except ValueError:
            pass
    return DEFAULT_MISS_COST


def bayes_escalation_threshold(
    base_threshold: float,
    cache_state: CacheState | None,
    family: str,
    *,
    miss_cost: float | None = None,
) -> float:
    """Compute Bayes-optimal posterior threshold ``tau_f*(L_at_risk, w_f)`` for mid-session escalation.

    Minimizes expected token-equivalent loss between:
      - Unlocking unnecessarily: ``L_at_risk * write_premium + LOCK_IN_READ_FACTOR * w_f``
      - Keeping locked when needed: ``C_miss``
    Satisfies exact boundary identities:
      - ``tau_f*(0, w_f) == base_threshold`` (cold start or expired cache)
      - ``0 < base_threshold < 1  ==>  base_threshold <= tau_f* < 1``
      - Monotone non-decreasing in both ``L_at_risk`` and ``w_f``.
    """
    if base_threshold <= 0.0:
        return 0.0
    if base_threshold >= 1.0:
        return 1.0
    if cache_state is None or cache_state.at_risk_tokens <= 0:
        return base_threshold
    c_miss = miss_cost if (miss_cost is not None and math.isfinite(miss_cost) and miss_cost > 0.0) else _miss_cost()
    w_f = max(0, FAMILY_SCHEMA_TOKENS.get(family, 0))
    break_cost = cache_state.at_risk_tokens * max(0.0, cache_state.write_premium) + LOCK_IN_READ_FACTOR * w_f
    base_odds = base_threshold / (1.0 - base_threshold)
    opt_odds = base_odds * (1.0 + break_cost / c_miss)
    return opt_odds / (1.0 + opt_odds)
