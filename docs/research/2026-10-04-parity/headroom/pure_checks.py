"""Isolated checks of pinned upstream pure functions; no package import or I/O services."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
SHA = "1cf496612e781ef8d67ff87ee4f78037492f0bc7"
SOURCE = ROOT / "source" / f"headroom-{SHA}"
results = []


def load(relative: str):
    name = "research_" + relative.replace("/", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(name, SOURCE / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def check(name, condition, detail=None):
    results.append({"name": name, "passed": bool(condition), "detail": detail})


# These modules were inspected before loading: only stdlib top-level imports.
# Bypass headroom/__init__.py, all pytest fixtures, native code and model loading.
fold = load("headroom/transforms/lossless_compaction.py")
segment = load("headroom/transforms/relevance_split.py")
lic = load("headroom/license_env.py")
headers = load("headroom/proxy/internal_header_policy.py")
counting = load("headroom/proxy/token_counting.py")

# Process-local flag only; no persistent environment/config change.
os.environ["HEADROOM_LOSSLESS_COMPACTION"] = "1"
text = ("A long repeated status line with details\n" * 12) + "FATAL E42\n"
compact = fold.compact_lossless(text, "log")
check("log shrinks", len(compact) < len(text), {"before_chars": len(text), "after_chars": len(compact)})
check("log exact inverse without ANSI", fold.expand_runs(compact) == text)
ansi = "\x1b[31mERROR red\x1b[0m\n" * 12
ansi_compact = fold.compact_lossless(ansi, "log")
check("ANSI log inverse equals stripped baseline", fold.expand_runs(ansi_compact) == fold.strip_ansi(ansi))
check("ANSI removal is not byte-lossless", fold.expand_runs(ansi_compact) != ansi)
search = "".join(f"src/long/directory/module.py:{i}:matched_{i}\n" for i in range(1, 25))
search_fold = fold.search_heading(search)
check("search heading shrinks", len(search_fold) < len(search))
check("search exact inverse", fold.search_unheading(search_fold) == search)
config = ("service:\n  retries: 3\n  enabled: true\n" * 15)
config_fold = fold.compact_lossless(config, "config")
check("config fold shrinks", len(config_fold) < len(config))
check("config exact inverse", fold.expand_runs(fold.unfold_repeated_blocks(config_fold)) == config)
diff = "diff --git a/a b/a\nindex 1234567..7654321 100644\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-old\n+new\n"
diff_fold = fold.compact_lossless(diff, "diff")
check("diff drops index metadata", "index 1234567" not in diff_fold and "-old\n+new\n" in diff_fold)
check("unknown fold passes through", fold.compact_lossless(text, "unknown") == text)
records = "record\n" + ("  indented continuation\n" * 150)
parts = segment.segment(records, max_chars=120)
check("relevance segmentation preserves exact bytes", "".join(parts) == records)
check("relevance segmentation bounds multiline records", all(len(p) <= 120 for p in parts))
one_line = "x" * 500
check("single overlong line remains whole", segment.segment(one_line, max_chars=120) == [one_line])
check("license usage report opt-in default", lic.usage_reporting_enabled({}) is False)
check("license usage report explicit on", lic.usage_reporting_enabled({"HEADROOM_USAGE_REPORTING": "on"}) is True)
check("current license variable", lic.resolve_license_token({"HEADROOM_LICENSE": "test-only"}) == "test-only")
check("internal header stripping default", headers.resolve_strip_internal_headers_mode(None) == "enabled")
check("internal credential detection", headers.is_credential_header("X-Headroom-Proxy-Token"))
check("internal headers removed", headers.strip_internal_headers({"X-Headroom-Proxy-Token": "test", "Accept": "application/json"}, mode="enabled") == {"Accept": "application/json"})
check("Gemini inclusive thinking not doubled", counting.gemini_output_tokens({"promptTokenCount": 10, "candidatesTokenCount": 9, "thoughtsTokenCount": 4, "totalTokenCount": 19}) == 9)
check("Gemini exclusive thinking added", counting.gemini_output_tokens({"promptTokenCount": 10, "candidatesTokenCount": 9, "thoughtsTokenCount": 4, "totalTokenCount": 23}) == 13)

# Extract one exact AST function, rather than import a provider module that can
# transitively initialize a package. This tests arithmetic, not integration.
tree = ast.parse((SOURCE / "headroom/backends/litellm.py").read_text(encoding="utf-8"))
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_anthropic_usage_from_litellm")
namespace = {"Any": Any}
exec(compile(ast.Module(body=[node], type_ignores=[]), "pinned_litellm_usage_function", "exec"), namespace)
mapped = namespace["_anthropic_usage_from_litellm"](SimpleNamespace(prompt_tokens=1000, completion_tokens=25, cache_read_input_tokens=700, cache_creation_input_tokens=200))
check("LiteLLM disjoint Anthropic input bucket", mapped == {"input_tokens": 100, "output_tokens": 25, "cache_read_input_tokens": 700, "cache_creation_input_tokens": 200}, mapped)
check("LiteLLM null usage fields zeroed", namespace["_anthropic_usage_from_litellm"](SimpleNamespace(prompt_tokens=None, completion_tokens=None)) == {"input_tokens": 0, "output_tokens": 0})

payload = {
    "date": "2026-10-04",
    "sha": SHA,
    "python": sys.version,
    "scope": "Researcher-authored stdlib-only isolated checks; not pytest, full-pipeline, Rust, ML, provider, or client integration verification.",
    "passed": sum(r["passed"] for r in results),
    "failed": sum(not r["passed"] for r in results),
    "results": results,
}
(ROOT / "pure-checks.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps({k: payload[k] for k in ("passed", "failed", "scope")}, indent=2))
sys.exit(bool(payload["failed"]))
