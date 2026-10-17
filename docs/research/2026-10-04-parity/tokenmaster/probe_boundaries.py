"""Read-only research probes against the pinned TokenMaster source snapshot.

No dependencies are installed and no provider or MCP service is started.
Only this evidence directory is written. The MCP decorator is a local shim:
wrapper function behavior is checked, NOT MCP transport or host integration.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SKILL = HERE / "source/token-master-plugin/skills/token-master"
sys.path.insert(0, str(SKILL))

from brainspace import tokens
from brainspace.benchmark import benchmark_one
from brainspace.ccr import CCR, parse_placeholders
from brainspace.compressors.code_compressor import _make_stub
from brainspace.router import route_typed

# Explicitly use the shipped dependency-free fallback; no tokenizer downloads.
tokens._TRIED = True
tokens._ENCODER = None


class DecoratorOnlyMCP:
    def __init__(self, name):
        self.name = name

    def tool(self):
        return lambda function: function


shim = types.ModuleType("mcp.server.fastmcp")
shim.FastMCP = DecoratorOnlyMCP
sys.modules["mcp"] = types.ModuleType("mcp")
sys.modules["mcp.server"] = types.ModuleType("mcp.server")
sys.modules["mcp.server.fastmcp"] = shim
spec = importlib.util.spec_from_file_location(
    "research_brainspace_mcp", SKILL / "brainspace_mcp.py"
)
mcp_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp_module)
ccr = CCR(HERE / "probe-ccr.sqlite")
mcp_module._STATE["ccr"] = ccr

results = []


def record(name, confirmed, **details):
    results.append({"probe": name, "confirmed": bool(confirmed), **details})


items = [{"id": n, "status": "ok"} for n in range(30)]
items[14] = {"id": 14, "status": "DENIED", "reason": "POLICY_SENTINEL_14"}
original = json.dumps(items, indent=2)
compressed, _ = route_typed(original, "fixture.json", stash=ccr.stash)
refs = parse_placeholders(compressed)
retrieved = [ccr.retrieve(ref) for ref in refs]
record(
    "json_middle_exception_hidden_but_retrievable",
    "POLICY_SENTINEL_14" not in compressed
    and any("POLICY_SENTINEL_14" in (text or "") for text in retrieved),
    output=compressed,
    references=refs,
    recovery_note="Omitted JSON slice is reserialized, not the full input bytes.",
)

failed_stash, _ = route_typed(
    original, "fixture.json", stash=lambda *args, **kwargs: None
)
record(
    "json_stash_failure_still_elides",
    failed_stash != original
    and "POLICY_SENTINEL_14" not in failed_stash
    and not parse_placeholders(failed_stash),
    output=failed_stash,
)

body = "first = 1\nsecond = 2\nreturn first + second\n"
stub = _make_stub(body, "example", stash=lambda *a, **k: None, indent=0)
record(
    "code_stub_stash_failure_still_elides",
    "return first + second" not in stub and not parse_placeholders(stub),
    output=stub,
    scope="Direct helper probe. Full AST path needs absent tree-sitter dependencies.",
)

log = "\n".join(
    [f"INFO completed ordinary step {i}" for i in range(20)]
    + ["FAILED test_security_boundary"]
    + [f"INFO completed ordinary step {i}" for i in range(21, 41)]
)
log_view, _ = route_typed(log, "pytest", stash=ccr.stash)
log_failed_stash, _ = route_typed(log, "pytest", stash=lambda *a, **k: None)
record(
    "log_failed_test_marker_hidden",
    "FAILED test_security_boundary" not in log_view,
    output=log_view,
    recovery_available=any(ccr.retrieve(ref) == log for ref in parse_placeholders(log_view)),
)
record(
    "log_stash_failure_preserves_original",
    log_failed_stash == log,
)

small_json = '{   "x":   1   }'
core, _ = route_typed(small_json, "fixture.json", stash=ccr.stash)
wrapped = mcp_module.brainspace_compress(small_json, "fixture.json")
record(
    "mcp_footer_bypasses_never_expand",
    tokens.estimate(core) < tokens.estimate(small_json)
    and tokens.estimate(wrapped) > tokens.estimate(small_json),
    tokens={"before": tokens.estimate(small_json), "core": tokens.estimate(core),
            "wrapped": tokens.estimate(wrapped), "backend": "heuristic"},
    output=wrapped,
    scope="Actual wrapper body; MCP decorator only is shimmed, no transport.",
)

hook_input = ("a" * 810) + "  b"
payload = {"tool_name": "Read", "tool_input": {"file_path": "fixture.md"},
           "tool_response": hook_input}
environment = os.environ.copy()
environment["BRAINSPACE_CCR"] = str(HERE / "hook-probe-ccr.sqlite")
environment["PYTHONDONTWRITEBYTECODE"] = "1"
environment["BRAINSPACE_HOOK_MIN_CHARS"] = "800"
environment["BRAINSPACE_HOOK_STDOUT_CAP"] = "9000"
environment["BRAINSPACE_HOOK_TOOLS"] = "Read"
proc = subprocess.run(
    [sys.executable, "-B", str(SKILL / "brainspace_posttooluse.py")],
    input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True,
    cwd=HERE, env=environment, check=False,
)
hook_output = json.loads(proc.stdout)["hookSpecificOutput"]["updatedToolOutput"]
record(
    "hook_footer_bypasses_never_expand",
    tokens.estimate(hook_output) > tokens.estimate(hook_input),
    tokens={"before": tokens.estimate(hook_input),
            "replacement": tokens.estimate(hook_output), "backend": "heuristic"},
    exit_code=proc.returncode,
    scope="Real hook subprocess output, NOT a live Claude Code request.",
)

structured_payload = {
    "tool_name": "Bash",
    "tool_response": {
        "stdout": log,
        "stderr": "diagnostic on stderr",
        "interrupted": False,
        "isImage": False,
    },
}
structured_environment = environment.copy()
structured_environment["BRAINSPACE_HOOK_TOOLS"] = "Bash"
structured_proc = subprocess.run(
    [sys.executable, "-B", str(SKILL / "brainspace_posttooluse.py")],
    input=json.dumps(structured_payload), text=True, encoding="utf-8", capture_output=True,
    cwd=HERE, env=structured_environment, check=False,
)
structured_replacement = json.loads(structured_proc.stdout)[
    "hookSpecificOutput"
]["updatedToolOutput"]
record(
    "structured_bash_input_replaced_with_plain_string",
    isinstance(structured_replacement, str)
    and "diagnostic on stderr" not in structured_replacement,
    input_shape="object: stdout, stderr, interrupted, isImage",
    output_shape=type(structured_replacement).__name__,
    scope="Actual hook subprocess output. Current official host docs say mismatched "
    "built-in output shapes are ignored; live host behavior was not tested.",
)


class BrokenRecovery:
    def __init__(self):
        self.retrieve_calls = 0

    def stash(self, text, **kwargs):
        return "[[BR:abcdef123456|json; 1L]]"

    def retrieve(self, reference):
        self.retrieve_calls += 1
        return None


broken = BrokenRecovery()
row = benchmark_one("broken-recovery", original, "fixture.json", broken)
record(
    "benchmark_recovery_check_skips_minted_hashes",
    row.lossless is True and broken.retrieve_calls == 0,
    reported_lossless=row.lossless,
    retrieve_calls=broken.retrieve_calls,
    reason="findall returns bare hashes; applying PLACEHOLDER_RE again always yields no match.",
)

large_original = "A" * 200001
reference = ccr.stash(large_original, ctype="prose")
returned = mcp_module.brainspace_retrieve(reference)
record(
    "mcp_retrieve_truncates_without_paging",
    ccr.retrieve(reference) == large_original
    and returned != large_original
    and "truncated at 200000 chars" in returned,
    original_characters=len(large_original),
    store_round_trip=True,
    mcp_return_characters=len(returned),
    scope="Actual wrapper body; no MCP transport.",
)

same_a = ccr.stash("identical text", ctype="code", source="alpha body")
same_b = ccr.stash("identical text", ctype="code", source="beta body")
record(
    "same_content_different_source_changes_placeholder",
    same_a != same_b and parse_placeholders(same_a) == parse_placeholders(same_b),
    first=same_a,
    second=same_b,
    meaning="Content key is stable; the full placeholder additionally depends on source metadata.",
)

report = {
    "as_of_date": "2026-10-04",
    "source_sha": "426fc853389ddba4bc6e1dd35a28179a895c064f",
    "python": sys.version,
    "tokenizer": "shipped chars/4 fallback explicitly selected",
    "scope": "Offline deterministic boundary probes; no model-quality or billed-cost measurement.",
    "results": results,
}
(HERE / "boundary-probe-results.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
for result in results:
    print(f"{'CONFIRMED' if result['confirmed'] else 'NOT CONFIRMED'} {result['probe']}")
raise SystemExit(0 if all(r["confirmed"] for r in results) else 1)
