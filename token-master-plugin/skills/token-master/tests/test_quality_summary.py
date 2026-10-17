import importlib.util
import os
from pathlib import Path


path = Path(__file__).resolve().parents[3] / "evals/run_quality.py"
spec = importlib.util.spec_from_file_location("run_quality", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(success=True, totals=True):
    return {
        "arm": {"name": "baseline"}, "grade": {"success": success}, "elapsed_seconds": 1,
        "totals": {"input_tokens": 10, "output_tokens": 4, "calls": 2,
                   "peak_input_tokens": 7} if totals else None,
    }


def test_unknown_outcome_never_becomes_a_defined_success_ratio():
    result = module.summarize([row(), row(None)])["baseline"]
    assert result["total_tokens"] == 28
    assert result["tokens_per_verified_success"] is None
    assert result["ungraded"] == 1


def test_partial_capture_does_not_report_subset_as_total():
    result = module.summarize([row(), row(False, False)])["baseline"]
    assert result["total_tokens"] is None
    assert result["calls"] is None
    assert result["failures"] == 1
    assert result["incomplete_traces"] == 1


def test_failures_count_in_descriptive_ratio_but_not_success_denominator():
    result = module.summarize([row(), row(False)])["baseline"]
    assert result["total_tokens"] == result["tokens_per_verified_success"] == 28
    assert result["ratio_status"] == "descriptive_only"


def test_child_environment_keeps_windows_systemroot_not_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("SystemRoot", os.environ.get("SystemRoot", r"C:\Windows"))
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-copy")
    monkeypatch.setenv("TYPESAFE_API_KEY", "do-not-copy")
    monkeypatch.setenv("GITHUB_TOKEN", "do-not-copy")
    env = module.child_environment(tmp_path)
    assert env["SystemRoot"] == os.environ["SystemRoot"]
    assert all("do-not-copy" != value for value in env.values())
    assert env["BRAINSPACE_TOKENIZER_FILE"].endswith("cl100k_base.tiktoken")


def test_environment_failure_cannot_look_like_valid_comparison():
    failed = row(False)
    failed["regime_valid"] = False
    result = module.summarize([row(), failed])["baseline"]
    assert result["invalid_environment_runs"] == 1
    assert result["tokens_per_verified_success"] is None
    assert result["ratio_status"] == "invalid_environment"
