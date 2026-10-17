"""Recovery-required successful-log overviews; exact output by default.

Unknown records, warnings, errors, FAILED/XPASS and nonzero exit diagnostics
remain whole-input passthrough, preserving all causal context. Only an explicit
overview of recognized INFO/DEBUG output ending in success can omit lines.
"""

from __future__ import annotations

import re

from . import report_failure, require_stash


_ALERT = re.compile(
    r"\b(?:\w*ERRORS?|\w*EXCEPTION|FATAL|CRITICAL|WARN(?:ING)?|TRACEBACK|FAIL(?:ED|URE|URES)?|"
    r"XPASS|DENIED|STDERR|UNKNOWN|CANCELLED|CANCELED|INTERRUPTED|ABORTED|PANIC|"
    r"TIMEOUT|TIMED OUT|UNSUCCESSFUL)\b",
    re.IGNORECASE,
)
_RECORD = re.compile(r"^\[(?:INFO|DEBUG)\] (.*)$")
_SUCCESS = re.compile(r"(?:build|tests?|process) (?:succeeded|passed|completed successfully)|exit code[:= ]+0", re.I)


def compress_logs(
    content: str,
    *,
    stash=None,
    context: int = 2,
    intent: str = "conservative",
    **opts,
) -> str:
    """Return an explicitly lossy, root-recoverable successful-log overview.

    ``context`` controls the head/tail window only; it never bounds the causal
    context retained on failures. Protected/unknown intents, malformed options
    and recovery failure return the original unchanged.
    """
    if not isinstance(content, str) or intent != "overview" or stash is None:
        return content
    try:
        if type(context) is not int or context < 0:
            return content
        lines = content.splitlines(keepends=True)
        window = max(1, context + 1)
        if len(lines) <= max(5, 2 * window + 1):
            return content
        if _ALERT.search(content):
            return content
        records = []
        for line in lines:
            match = _RECORD.fullmatch(line.rstrip("\r\n"))
            if match is None:
                return content
            records.append(match[1])
        if not _SUCCESS.fullmatch(records[-1]):
            return content
        # Even a known level does not make a nonzero or unknown exit safe.
        if any(re.search(r"\b(?:exit|exited|status|state|returncode|code)\b", record, re.I)
               and not _SUCCESS.fullmatch(record) for record in records):
            return content
        reference = require_stash(content, stash=stash, ctype="log",
                                  source="full original", kind="root")
        omitted = len(lines) - 2 * window
        view = ("".join(lines[:window]) + f"... overview (lossy): {omitted} lines elided ...\n" +
                "".join(lines[-window:]))
        if not view.endswith("\n"):
            view += "\n"
        view += f"full log: {reference}\n"
        return view if len(view) < len(content) else content
    except Exception as exc:
        report_failure(opts, exc)
        return content
