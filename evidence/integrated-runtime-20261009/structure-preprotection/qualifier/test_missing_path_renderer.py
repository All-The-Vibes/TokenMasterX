"""Pinned failed-view rendering regressions; no native or filesystem lookup."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checks import assess, observed
from test_checks import exact_evidence


def recorded():
    fixture = json.loads(Path(__file__).with_name("fixtures").joinpath("native-003-missing-path.json").read_text("utf-8"))
    assert fixture["provenance"]["native_version"] == "1.0.95-0"
    assert fixture["provenance"]["renderer"] == "native-view-missing-path-1.0.95-v1"
    return fixture


def set_delivery(data, text):
    for prep in data["preparations"]:
        for key in ("original", "prepared"):
            for message in prep[key]["messages"]:
                if message["tool_call_id"] == "exact_missing":
                    message["content"] = text
    for request, capture in zip(data["requests"], data["captures"]):
        for item in request["body"]["input"]:
            if item["call_id"] == "exact_missing":
                item["output"] = text
        capture["input"] = json.dumps(request["body"])


def evidence(shape="omitted"):
    """Combine captured failed event with synthetic checker-only surrounding rows."""
    fixture = recorded()
    data = exact_evidence()
    data["planned"][1] = deepcopy(fixture["action"])
    data["emitted"] = deepcopy(data["planned"])
    data["events"] = data["events"][:2] + deepcopy(fixture["events"])
    if shape == "null":
        data["events"][-1]["data"]["result"] = None
    set_delivery(data, fixture["delivered_text"])
    return data


@pytest.mark.parametrize("shape", ["omitted", "null"])
def test_pinned_missing_path_renderer_matches_recorded_delivery_exactly(shape):
    data = evidence(shape)
    expected = recorded()["delivered_text"]
    assert observed(data["events"], data["planned"][1], success=False) == expected
    assert data["events"][-1]["data"]["success"] is False


@pytest.mark.parametrize("shape", ["omitted", "null"])
def test_exact_cell_accepts_pinned_rendering_without_adding_source_authority(shape):
    data = evidence(shape)
    assert assess(**data)["controls"] == ["exact", "status"]
    assert data["native"]["runtime"]["source_read_receipts"] == 1
    data["native"]["runtime"]["source_read_receipts"] = 2
    with pytest.raises(ValueError, match="unexpected_ranged_or_failure_source_receipts"):
        assess(**data)


@pytest.mark.parametrize("mutation", [
    "event_path", "code", "message", "command", "view_type", "resolved_true",
    "resolved_boolean", "resolved_capitalized", "missing_properties",
    "null_telemetry", "list_properties", "success", "rte",
])
def test_pinned_renderer_does_not_generalize_to_other_event_shapes(mutation):
    data = evidence()
    start, end = data["events"][-2]["data"], data["events"][-1]["data"]
    props = end["toolTelemetry"]["properties"]
    if mutation == "event_path":
        start["arguments"]["path"] += ".wrong"
    elif mutation == "code":
        end["error"]["code"] = "not_found"
    elif mutation == "message":
        end["error"]["message"] = "Path does not exist."
    elif mutation == "command":
        props["command"] = "read"
    elif mutation == "view_type":
        props["viewType"] = "file"
    elif mutation == "resolved_true":
        props["resolvedPathAgainstCwd"] = "true"
    elif mutation == "resolved_boolean":
        props["resolvedPathAgainstCwd"] = False
    elif mutation == "resolved_capitalized":
        props["resolvedPathAgainstCwd"] = "False"
    elif mutation == "missing_properties":
        end["toolTelemetry"].pop("properties")
    elif mutation == "null_telemetry":
        end["toolTelemetry"] = None
    elif mutation == "list_properties":
        end["toolTelemetry"]["properties"] = []
    else:
        end[mutation] = True
    with pytest.raises(ValueError):
        assess(**data)


@pytest.mark.parametrize("mutation", ["path", "prefix", "first_period", "last_period", "spacing", "literal_only"])
def test_missing_path_delivery_must_keep_exact_path_and_punctuation(mutation):
    data = evidence()
    text = recorded()["delivered_text"]
    changed = {
        "path": text.replace("missing-status-control.md", "different.md"),
        "prefix": "Error: " + text,
        "first_period": text.replace("exist.", "exist"),
        "last_period": text[:-1],
        "spacing": text.replace(". Please", ".  Please"),
        "literal_only": "Path does not exist",
    }[mutation]
    # All ingress/preparation/capture records agree; the event is the only oracle.
    set_delivery(data, changed)
    with pytest.raises(ValueError, match="ingress_not_observed_result"):
        assess(**data)


@pytest.mark.parametrize("path", ["relative.md", "", "C:relative.md", "C:/" + "x" * 4097, "C:/bad\0path", None])
def test_renderer_requires_a_bounded_absolute_frozen_path(path):
    data = evidence()
    data["planned"][1]["arguments"]["path"] = path
    data["emitted"][1]["arguments"]["path"] = path
    data["events"][-2]["data"]["arguments"]["path"] = path
    set_delivery(data, f"Path {path} does not exist. Please provide a valid path.")
    with pytest.raises(ValueError, match="ingress_not_observed_result"):
        assess(**data)


def test_explicit_plain_result_content_is_not_overridden_by_missing_path_renderer():
    data = evidence()
    data["events"][-1]["data"]["result"] = {"content": "direct native failure text"}
    assert observed(data["events"], data["planned"][1], success=False) == "direct native failure text"
    with pytest.raises(ValueError, match="ingress_not_observed_result"):
        assess(**data)


def test_pinned_renderer_uses_frozen_arguments_without_reading_path(monkeypatch):
    fixture = recorded()

    def forbidden(*_, **__):
        raise AssertionError("renderer must not inspect filesystem")
    with monkeypatch.context() as guard:
        for name in ("read_bytes", "read_text", "exists", "stat", "resolve"):
            guard.setattr(Path, name, forbidden)
        actual = observed(fixture["events"], fixture["action"], success=False)
    assert actual == fixture["delivered_text"]
