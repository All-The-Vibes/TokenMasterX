from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.candidate_audit import audit_threshold_decrease  # noqa: E402
from brainspace.ccr import CCR  # noqa: E402
from brainspace.request_policy import RequestPolicy  # noqa: E402


def test_other_policy_mutations_are_not_mistaken_for_equivalent(tmp_path):
    policy = RequestPolicy(enabled=True, min_tool_chars=512)
    result = audit_threshold_decrease(policy, replace(policy, keep_recent_tool_results=2),
                                      [], intent="overview", store=CCR(workspace_root=tmp_path))
    assert result["decision"] == "not_assessed_other_mutation"
    assert result["could_change_observed_views"] is None


def test_new_band_eligibility_is_observed_without_model_calls(tmp_path):
    policy = RequestPolicy(enabled=True, min_tool_chars=512)
    text = '{"data":' + " " * 390 + "[1,2,3]}"
    request = json.dumps({"input": [
        {"role": "user", "content": "overview"},
        {"type": "function_call_output", "output": text},
        {"type": "function_call_output", "output": "recent"},
    ]})
    result = audit_threshold_decrease(policy, replace(policy, min_tool_chars=384),
                                      [request], intent="overview", store=CCR(workspace_root=tmp_path))
    assert result["could_change_observed_views"]
    assert result["model_calls"] == 0
    assert not result["global_equivalence_proved"]
    assert not result["quality_certified"]


def test_protected_task_is_not_transformed(tmp_path):
    policy = RequestPolicy(enabled=True, min_tool_chars=512)
    result = audit_threshold_decrease(policy, replace(policy, min_tool_chars=384),
                                      ["not parsed for exact intent"], intent="exact",
                                      store=CCR(workspace_root=tmp_path))
    assert result["decision"] == "protected_intent"
    assert not result["could_change_observed_views"]
