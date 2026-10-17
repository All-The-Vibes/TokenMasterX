"""Search-only activation audit; not counterfactual generation or certification."""
from dataclasses import asdict
import hashlib
import json

from brainspace.request_policy import RequestPolicy
from brainspace.router import route_typed


def audit_threshold_decrease(incumbent, candidate, request_texts, *, intent, store):
    """Check newly eligible forwarded tool text for a threshold-only decrease.

    Other mutations are deliberately not assessed: forwarded traces may already
    contain views, so they cannot prove what a different retention policy would
    have kept. Unknown future branches and model randomness are not replayed.
    """
    if not isinstance(incumbent, RequestPolicy) or not isinstance(candidate, RequestPolicy):
        raise ValueError("validated policies required")
    before, after = asdict(incumbent), asdict(candidate)
    changed = [key for key in before if before[key] != after[key]]
    report = {
        "changed_fields": changed, "scope": "observed forwarded search traces only",
        "request_count": len(request_texts), "new_band_candidates": [],
        "could_change_observed_views": None, "global_equivalence_proved": False,
        "quality_certified": False, "model_calls": 0,
    }
    if changed != ["min_tool_chars"] or candidate.min_tool_chars >= incumbent.min_tool_chars:
        return dict(report, decision="not_assessed_other_mutation")
    if intent not in ("navigation", "overview"):
        return dict(report, could_change_observed_views=False, decision="protected_intent")
    for request_no, text in enumerate(request_texts):
        request = json.loads(text)
        items = request["input"]
        stage = sum(item.get("role") == "user" for item in items) - 1
        if stage > 0:
            continue  # this challenge runner explicitly switches followups to exact
        outputs = [item for item in items if item.get("type") == "function_call_output"]
        for item in outputs[:-incumbent.keep_recent_tool_results]:
            content = item["output"]
            if candidate.min_tool_chars <= len(content) < incumbent.min_tool_chars:
                diagnostics = {}
                view, _ = route_typed(content, stash=store.stash, intent=intent, diagnostics=diagnostics)
                report["new_band_candidates"].append({
                    "request": request_no, "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "chars": len(content), "router_changed_text": view != content,
                    "diagnostic": diagnostics,
                })
    report["could_change_observed_views"] = any(
        item["router_changed_text"] for item in report["new_band_candidates"])
    report["decision"] = (
        "new_activation_possible_requires_fresh_evaluation" if report["could_change_observed_views"]
        else "no_new_activation_on_observed_trace")
    return report
