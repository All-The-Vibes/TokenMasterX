"""Read-only production-code probes for the October 4, 2026 research review.

Writes research evidence beside this file. All CCR databases and graph fixtures
are temporary. No host configuration, source code, or paid API is changed.
Run with an existing Python environment containing MCP; no install is performed.
"""
from __future__ import annotations

import gc
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "token-master-plugin" / "skills" / "token-master"
sys.path.insert(0, str(SKILL))
sys.dont_write_bytecode = True

from brainspace import tokens
from brainspace.benchmark import benchmark_one
from brainspace.ccr import CCR, PLACEHOLDER_RE
from brainspace.router import route_typed
import brainspace_mcp
import graphify_mcp


def package_version(name: str):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


class BrokenReadCCR(CCR):
    def __init__(self, path):
        super().__init__(path)
        self.read_calls = 0

    def retrieve(self, ref):
        self.read_calls += 1
        return None


def main():
    evidence = {
        "research_date": "2026-10-04",
        "repository": str(ROOT),
        "commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "python": sys.executable,
        "python_version": sys.version,
        "packages": {
            name: package_version(name)
            for name in (
                "mcp", "pytest", "tiktoken", "tree-sitter",
                "tree-sitter-python", "tree-sitter-rust"
            )
        },
        "token_measurement": tokens.reduction("hello world", "hello")["backend"],
        "scope": "Local function and hook subprocess probes; no live host or model run.",
    }

    with tempfile.TemporaryDirectory(prefix="tokenmaster-research-") as tmp:
        tmp = Path(tmp)
        ccr = CCR(tmp / "ccr.sqlite")
        brainspace_mcp._STATE["ccr"] = ccr

        # The shipped benchmark parses already-extracted hashes as placeholders.
        # An unreadable store should fail recovery validation, not report success.
        log = "\n".join(
            f"[INFO] Processed work item {i:04d} successfully" for i in range(300)
        )
        broken = BrokenReadCCR(tmp / "broken.sqlite")
        compressed_log, _ = route_typed(log, "fixture.log", stash=broken.stash)
        row = benchmark_one("fixture.log", log, "fixture.log", broken)
        evidence["recovery_validator"] = {
            "placeholders_in_compressed_view": len(PLACEHOLDER_RE.findall(compressed_log)),
            "stored_entries": broken.stats()["entries"],
            "benchmark_reports_lossless": row.lossless,
            "retrieve_calls_made_by_benchmark": broken.read_calls,
            "fault_injection": "CCR.retrieve always returns None.",
            "finding_reproduced": bool(PLACEHOLDER_RE.findall(compressed_log))
            and row.lossless and broken.read_calls == 0,
        }

        # Check the actual emitted result, not only route_typed's inner result.
        body = "Ordinary plain words stay exactly as written. " * 23
        candidate = None
        for spaces in range(5, 80):
            original = "alpha" + " " * spaces + "beta\n" + body
            compressed, _ = route_typed(original, "fixture.md", stash=ccr.stash)
            if compressed == original:
                continue
            emitted = brainspace_mcp.brainspace_compress(original, "fixture.md")
            if tokens.estimate(emitted) > tokens.estimate(original):
                candidate = (original, compressed, emitted)
                break
        assert candidate is not None, "No footer-expansion fixture found in this runtime."
        original, compressed, emitted = candidate
        env = dict(os.environ)
        env["BRAINSPACE_CCR"] = str(tmp / "hook.sqlite")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        payload = {
            "tool_name": "Read",
            "tool_input": {"file_path": "fixture.md"},
            "tool_response": original,
        }
        hook = subprocess.run(
            [sys.executable, str(SKILL / "brainspace_posttooluse.py")],
            input=json.dumps(payload), text=True, capture_output=True,
            check=True, env=env,
        )
        hook_text = json.loads(hook.stdout)["hookSpecificOutput"]["updatedToolOutput"]
        evidence["final_response_expansion"] = {
            "backend": evidence["token_measurement"],
            "input_characters": len(original),
            "input_estimated_tokens": tokens.estimate(original),
            "core_compressed_estimated_tokens": tokens.estimate(compressed),
            "mcp_emitted_estimated_tokens": tokens.estimate(emitted),
            "hook_emitted_estimated_tokens": tokens.estimate(hook_text),
            "mcp_expands": tokens.estimate(emitted) > tokens.estimate(original),
            "hook_expands": tokens.estimate(hook_text) > tokens.estimate(original),
            "qualification": "Real entry points; character-based shipped fallback, not provider billing.",
        }

        structured_response = {
            "stdout": log,
            "stderr": "",
            "interrupted": False,
            "isImage": False,
        }
        structured_hook = subprocess.run(
            [sys.executable, str(SKILL / "brainspace_posttooluse.py")],
            input=json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": "fixture only; not executed"},
                "tool_response": structured_response,
            }),
            text=True, capture_output=True, check=True, env=env,
        )
        replacement = json.loads(structured_hook.stdout)["hookSpecificOutput"]["updatedToolOutput"]
        evidence["structured_hook_shape"] = {
            "original_response_type": type(structured_response).__name__,
            "emitted_replacement_type": type(replacement).__name__,
            "preserves_response_shape": isinstance(replacement, dict),
            "qualification": "Subprocess output verified; current host acceptance is a documentation-based inference, not a live host test.",
        }

        # A Markdown code fence can carry meaningful whitespace inside a literal.
        markdown = (
            "This example requires exact string content:\n```python\n"
            'assert "alpha                    beta" != "alpha beta"\n```\n'
        )
        compact, _ = route_typed(markdown, "fixture.md", stash=ccr.stash)
        evidence["prose_literal_preservation"] = {
            "input": markdown,
            "output": compact,
            "changed": compact != markdown,
            "input_has_distinct_string_literals": "alpha                    beta" in markdown,
            "output_has_false_assertion": 'assert "alpha beta" != "alpha beta"' in compact,
            "recovery_placeholder_present": bool(PLACEHOLDER_RE.findall(compact)),
            "finding_reproduced": 'assert "alpha beta" != "alpha beta"' in compact
            and not PLACEHOLDER_RE.findall(compact),
        }

        # CCR storage recovery is not identical to MCP delivery recovery.
        large_original = "A" * (brainspace_mcp.MAX_RETRIEVE_CHARS + 100)
        ref = ccr.stash(large_original, ctype="prose", source="large-fixture")
        direct = ccr.retrieve(ref)
        delivered = brainspace_mcp.brainspace_retrieve(ref)
        evidence["retrieval_delivery"] = {
            "input_characters": len(large_original),
            "configured_cap": brainspace_mcp.MAX_RETRIEVE_CHARS,
            "direct_CCR_exact": direct == large_original,
            "MCP_exact": delivered == large_original,
            "MCP_characters": len(delivered),
            "truncation_notice_present": "truncated at" in delivered,
        }

        # Placeholders are deterministic for fixed content AND fixed metadata.
        ref_a = ccr.stash("identical content", source="source-A")
        ref_b = ccr.stash("identical content", source="source-B")
        evidence["placeholder_identity"] = {
            "same_content_and_hash": PLACEHOLDER_RE.findall(ref_a) == PLACEHOLDER_RE.findall(ref_b),
            "different_source_metadata": True,
            "byte_identical_placeholders": ref_a == ref_b,
        }

        # The graph is cached once in process; changing the file does not reload it.
        graph_path = tmp / "graph.json"
        graph = {
            "nodes": [{
                "id": "n1", "label": "old_symbol", "file_type": "code",
                "source_file": "fixture.py", "source_location": 1
            }],
            "links": [],
        }
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        graphify_mcp.GRAPH_PATH = str(graph_path)
        assert graphify_mcp._ensure_loaded() is None
        graph["nodes"][0]["label"] = "new_symbol"
        graph_path.write_text(json.dumps(graph), encoding="utf-8")
        assert graphify_mcp._ensure_loaded() is None
        evidence["graph_freshness"] = {
            "on_disk_symbol": "new_symbol",
            "in_process_symbol": graphify_mcp._STATE["NODES"]["n1"]["label"],
            "reloads_after_file_change": bool(graphify_mcp._resolve("new_symbol")),
        }
        # The production store uses SQLite transaction context managers, which
        # do not explicitly close connections. Collect them before Windows temp
        # cleanup; this is confined to the research harness.
        gc.collect()

    # Synthetic rate example, deliberately not a current provider price quote.
    uncached_rate = 1.0
    cached_rate = 0.1
    baseline = 1_000 * uncached_rate + 9_000 * cached_rate
    transition = 5_000 * uncached_rate
    compressed_warm = 500 * uncached_rate + 4_500 * cached_rate
    evidence["illustrative_cache_economics"] = {
        "synthetic_not_measured": True,
        "rates": {"uncached": uncached_rate, "cache_read": cached_rate},
        "baseline_warm_tokens": 10_000,
        "compressed_tokens": 5_000,
        "baseline_warm_cost_units": baseline,
        "compressed_cache_miss_cost_units": transition,
        "transition_cost_ratio": transition / baseline,
        "compressed_warm_cost_units": compressed_warm,
        "requests_until_total_cost_break_even": next(
            n for n in range(1, 100)
            if transition + (n - 1) * compressed_warm < n * baseline
        ),
        "assumptions": "One cache-invalidating transition, then repeated warm requests; zero compression overhead; no quality change.",
    }
    target = Path(__file__).with_name("local-audit.json")
    target.write_text(json.dumps(evidence, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
