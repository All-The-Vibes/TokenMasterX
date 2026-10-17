"""Synthetic frozen-study replay. No network/model calls are permitted."""
from dataclasses import fields, replace
from itertools import count
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
import run_refinement as runner  # noqa: E402
from refinement import core  # noqa: E402
from refinement.audit import audit_study  # noqa: E402
from refinement.cases import generate_cases  # noqa: E402
from quality.responses import Reply, ResponsesTransport  # noqa: E402

RESPONSE_IDS = count()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def edit(path, **changes):
    value = read(path)
    value.update(changes)
    core.write_json(path, value)


def response(client, payload, text, *, usage=True):
    body = dict(object="response", model=client.model, status="completed",
                id=f"synthetic-response-{next(RESPONSE_IDS)}",
                output=[dict(type="reasoning", encrypted_content="opaque-ciphertext-is-counted"),
                        dict(type="message", role="assistant",
                             content=[dict(type="output_text", text=text)])])
    if usage:
        body["usage"] = dict(input_tokens=10, output_tokens=5, total_tokens=15)
    return Reply(True, "ok", True, core.wire(client.request(payload)), core.wire(body), body, 200, 0)


def build(output, monkeypatch, *, primary=True, secondary=True, failure=None, usage=True,
          secondary_http_status=None):
    frozen = runner.freeze(output)
    args = SimpleNamespace(output=output, primary="model-A", secondary="model-B", seed=123,
                           tasks=4, max_output_tokens=1024, call_seconds=60, policy_seconds=240,
                           max_total_calls=58, study_seconds=1200, reference_stop=500000,
                           base_url="http://127.0.0.1:15721/v1", allow_network=False)
    with monkeypatch.context() as patch:
        patch.setattr(runner, "__file__", str(frozen))
        assert runner.execute(args) == 0
    # The real prepared manifest is immutable for the synthetic capture phase.
    manifest = read(output / "manifest.json")
    cases = {c.id: c for c in generate_cases(args.seed, args.tasks)}
    arms = {a.name: a for a in core.arms(args.primary, args.secondary)}
    ready = {}
    for label, passed in (("primary", primary), ("secondary", secondary)):
        client = ResponsesTransport(args.base_url, getattr(args, label), max_output_tokens=128)

        def readiness(c, p, s):
            reply = response(c, p, "READY" if passed else "NOT READY", usage=usage)
            return (replace(reply, ok=False, reason="http_error", http_status=secondary_http_status)
                    if label == "secondary" and secondary_http_status is not None else reply)

        core.capture_call(client, runner.READINESS, output / "preflight" / label,
                          stage="readiness", seconds=60, invoke=readiness)
        ready[label] = passed
        if not passed and label == "primary":
            break
    core.write_json(output / "readiness.json", ready)
    clients = {model: ResponsesTransport(args.base_url, model, max_output_tokens=1024)
               for model in (args.primary, args.secondary)}
    for case_id, name in manifest["schedule"]:
        arm, case = arms[name], cases[case_id]
        if not primary or not secondary and arm.writer != arm.critic or not secondary and arm.writer != args.primary:
            continue

        def invoke(client, payload, seconds):
            if failure == "invalid":
                text = "not valid json"
            elif core.STAGES["critique"] in payload["instructions"]:
                text = core.wire({"critique": "Checked the supplied solution."})
            else:
                text = core.wire({"answer": case.expected, "explanation": "Synthetic fixture."})
            reply = response(client, payload, text, usage=usage)
            if failure == "http":
                return replace(reply, ok=False, reason="http_error", http_status=503)
            if failure == "model":
                body = dict(reply.body, model="unavailable-substitute")
                return replace(reply, ok=False, reason="model_mismatch", body=body, output_text=core.wire(body))
            if failure == "incomplete":
                return replace(reply, ok=False, reason="transport_error", complete=False, body=None,
                               output_text=None, http_status=None, error_type="TimeoutError")
            if failure == "output_limit":
                body = dict(reply.body, usage=dict(input_tokens=10, output_tokens=1025, total_tokens=1035))
                return replace(reply, body=body, output_text=core.wire(body))
            return reply

        core.run_policy(case.prompt, arm, output / "runs" / case_id / name, clients, core.Limits(),
                        reserve=lambda count, seconds: seconds if secondary_http_status is None else 0,
                        observe=lambda record: None, invoke=invoke)
        if secondary_http_status is not None:
            break
    return output


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network/model call forbidden")
    monkeypatch.setattr(ResponsesTransport, "call", forbidden)
    monkeypatch.setattr(core, "deadline_call", forbidden)


@pytest.fixture
def study(tmp_path, monkeypatch):
    return build(tmp_path / "study", monkeypatch)


def test_full_study_counts_and_runner_compatibility(study):
    report = audit_study(study)
    assert report["audit_status"] == "consistent", report["errors"]
    assert len(report["per_task"]) == 20
    assert report["all_in"]["tasks"] == report["all_in"]["correct"] == 20
    assert report["all_in"]["calls"] == 58
    assert report["preflight"]["calls"] == 2
    assert sum(arm["calls"] for arm in report["by_arm"].values()) == 56
    assert report["all_in"]["bridge_reported_tokens"] == 58 * 15
    assert report["all_in"]["bridge_by_model"] == {
        "model-A": dict(input_tokens=490, output_tokens=245, total_tokens=735),
        "model-B": dict(input_tokens=90, output_tokens=45, total_tokens=135)}
    assert report["all_in"]["reference_tokens"] > report["all_in"]["visible_tokens"]
    assert report["all_in"]["wall_seconds"] == sum(row["wall_seconds"] for row in report["per_task"])
    assert report["by_arm"]["single_primary"]["tokens_per_correct"] > 0
    assert report["population_certificate"] is False
    assert report["weights_provider_independently_authenticated"] is False
    assert "raw sum" in report["bridge_reported_tokens_basis"]
    assert "recorded" in report["wall_seconds_basis"]
    assert 'audit["audit_status"] == "consistent"' in Path(runner.__file__).read_text()


@pytest.mark.parametrize("target", ["planned", "input", "model", "outcome", "measurement", "stage"])
def test_capture_tampering(study, target):
    directory = next((study / "runs").glob("*/single_primary"))
    if target == "planned":
        path = directory / "call-00/started.json"
        value = read(path)
        planned = json.loads(value["planned_request"])
        planned["max_output_tokens"] += 1
        value["planned_request"] = core.wire(planned)
        value["planned_request_sha256"] = runner.file_hash(path)  # attacker cannot evade reconstruction
        core.write_json(path, value)
    elif target == "input":
        path = directory / "call-00/reply.json"
        edit(path, input_text=read(path)["input_text"] + " ")
    elif target == "model":
        path = directory / "call-00/reply.json"
        body = json.loads(read(path)["output_text"])
        body["model"] = "forged-model"
        edit(path, output_text=core.wire(body))
    elif target == "outcome":
        edit(directory / "result.json", answer="99999")
    elif target == "stage":
        edit(directory / "result.json", stage_answers=["99999"])
    else:
        path = directory / "call-00/reply.json"
        measurement = read(path)["measurement"]
        measurement["reference_total"] = 0
        edit(path, measurement=measurement)
    assert audit_study(study)["audit_status"] == "inconsistent"


@pytest.mark.parametrize("target", ["source", "cases", "case_identity", "arms", "schedule", "limits"])
def test_frozen_control_tampering(study, target):
    if target == "source":
        path = study / "source/token-master-plugin/evals/refinement/core.py"
        path.write_text("raise RuntimeError('must never execute')", encoding="utf-8")
    elif target in ("cases", "case_identity"):
        path = study / "cases.json"
        cases = read(path)
        cases[0]["prompt"] = "substituted prompt"
        core.write_json(path, cases)
        if target == "case_identity":
            edit(study / "manifest.json", cases_sha256=runner.file_hash(path))
    else:
        path = study / "manifest.json"
        value = read(path)
        if target == "arms":
            value["arms"][0]["writer"] = "model-B"
        elif target == "schedule":
            value["schedule"].append(value["schedule"][0])
        else:
            value["limits"]["max_output_tokens"] = 1
        core.write_json(path, value)
    assert audit_study(study)["audit_status"] == "inconsistent"


@pytest.mark.parametrize("key,value", [
    ("tokenizer_version", "forged-version"), ("protocol_id", "forged-protocol"),
    ("protocol_version", "999"), ("vocabulary_id", "0" * 64),
    ("exact_reference", 1), ("provider_native", True),
])
def test_tokenizer_metadata_must_match_exactly(study, key, value):
    path = study / "manifest.json"
    tokenizer = read(path)["tokenizer"]
    tokenizer[key] = value
    edit(path, tokenizer=tokenizer)
    report = audit_study(study)
    assert report["audit_status"] == "inconsistent"
    assert "tokenizer metadata mismatch" in report["errors"]


def rewrite_body(path, change):
    record = read(path)
    body = json.loads(record["output_text"])
    change(body)
    record["output_text"] = core.wire(body)
    reply = Reply(**{field.name: record[field.name] for field in fields(Reply)
                     if field.name != "body"}, body=body)
    record["measurement"] = core.recount(reply)
    core.write_json(path, record)


@pytest.mark.parametrize("pair", ["preflight-preflight", "preflight-task", "task-task"])
def test_duplicate_successful_response_ids(study, pair):
    source = study / "preflight/primary/reply.json"
    destination = study / "preflight/secondary/reply.json"
    task = next((study / "runs").glob("*/resample_primary"))
    if pair == "preflight-task":
        destination = task / "call-00/reply.json"
    elif pair == "task-task":
        source, destination = task / "call-00/reply.json", task / "call-01/reply.json"
    response_id = json.loads(read(source)["output_text"])["id"]
    rewrite_body(destination, lambda body: body.update(id=response_id))
    report = audit_study(study)
    assert report["audit_status"] == "inconsistent"
    assert any("duplicate successful response id" in error for error in report["errors"])


@pytest.mark.parametrize("empty", [None, ""])
def test_absent_response_ids_remain_an_explicit_limitation(study, empty):
    for path in study.rglob("reply.json"):
        rewrite_body(path, lambda body: body.pop("id") if empty is None else body.update(id=empty))
    report = audit_study(study)
    assert report["audit_status"] == "consistent", report["errors"]
    assert report["all_in"]["calls"] == 58
    assert report["weights_provider_independently_authenticated"] is False
    assert "absent IDs cannot be checked" in report["scope"]


@pytest.mark.parametrize("target", ["reply", "call", "run", "result"])
def test_missing_work_is_unknown_not_zero(study, target):
    directory = next((study / "runs").glob("*/single_primary"))
    if target == "reply":
        (directory / "call-00/reply.json").unlink()
    elif target == "call":
        shutil.rmtree(directory / "call-00")
    elif target == "run":
        shutil.rmtree(directory)
    else:
        (directory / "result.json").unlink()
    report = audit_study(study)
    assert report["audit_status"] == "incomplete", report["errors"]
    assert report["all_in"]["correct"] is None
    assert report["all_in"]["reference_tokens"] is None
    assert report["all_in"]["bridge_by_model"]["model-A"]["total_tokens"] is None
    assert len(report["per_task"]) == 20


@pytest.mark.parametrize("target", ["call", "run", "start", "result", "preflight"])
def test_extras_and_duplicate_evidence_are_rejected(study, target):
    directory = next((study / "runs").glob("*/single_primary"))
    if target == "call":
        shutil.copytree(directory / "call-00", directory / "call-01")
    elif target == "run":
        shutil.copytree(directory, directory.parent / "unknown_arm")
    elif target == "start":
        shutil.copyfile(directory / "call-00/started.json", directory / "started.json")
    elif target == "result":
        shutil.copyfile(directory / "result.json", directory / "call-00/result.json")
    else:
        shutil.copytree(study / "preflight/primary", study / "preflight/extra")
    assert audit_study(study)["audit_status"] == "inconsistent"


@pytest.mark.parametrize("failure", ["invalid", "http", "model", "output_limit"])
def test_recorded_failed_policies_are_consistent(tmp_path, monkeypatch, failure):
    report = audit_study(build(tmp_path / "study", monkeypatch, failure=failure))
    assert report["audit_status"] == "consistent", report["errors"]
    assert report["all_in"]["correct"] == 0
    assert report["all_in"]["calls"] == 22
    assert report["all_in"]["reference_tokens"] > 0
    assert report["all_in"]["tokens_per_correct"] is None


def test_incomplete_captures_not_free(tmp_path, monkeypatch):
    report = audit_study(build(tmp_path / "study", monkeypatch, failure="incomplete"))
    assert report["audit_status"] == "incomplete", report["errors"]
    assert report["all_in"]["calls"] == 22
    assert report["all_in"]["reference_tokens"] is None
    assert report["all_in"]["bridge_reported_tokens"] is None


def test_missing_native_usage_is_not_zero(tmp_path, monkeypatch):
    report = audit_study(build(tmp_path / "study", monkeypatch, usage=False))
    assert report["audit_status"] == "consistent", report["errors"]
    assert report["all_in"]["reference_tokens"] > 0
    assert report["all_in"]["bridge_reported_tokens"] is None
    assert all(usage["total_tokens"] is None for usage in report["all_in"]["bridge_by_model"].values())


@pytest.mark.parametrize("primary,secondary,expected", [(True, False, 12), (False, True, 0)])
def test_readiness_controls_inventory(tmp_path, monkeypatch, primary, secondary, expected):
    study = build(tmp_path / "study", monkeypatch, primary=primary, secondary=secondary)
    report = audit_study(study)
    assert report["audit_status"] == "consistent", report["errors"]
    assert report["all_in"]["tasks"] == expected
    if primary:
        assert set(report["by_arm"]) == {"single_primary", "resample_primary", "refine_primary"}
        edit(study / "readiness.json", secondary=True)
        assert audit_study(study)["audit_status"] == "inconsistent"


@pytest.mark.parametrize("status", [429, 503])
def test_secondary_readiness_429_supports_stop_but_not_missing_inventory(tmp_path, monkeypatch, status):
    report = audit_study(build(tmp_path / "study", monkeypatch, secondary=False,
                               secondary_http_status=status))
    assert report["audit_status"] == "incomplete", report["errors"]
    assert report["preflight"]["calls"] == 2
    assert len(report["per_task"]) == 12
    assert report["per_task"][0]["status"] == "study_limit"
    assert report["per_task"][0]["calls"] == 0
    assert all(row["status"] == "incomplete" for row in report["per_task"][1:])
    assert report["all_in"]["reference_tokens"] is None
    assert any("missing runs/" in error for error in report["errors"])
    assert any("study deadline lacks" in error for error in report["errors"]) == (status != 429)


def test_frozen_rate_limit_policy_cannot_change(study):
    edit(study / "manifest.json", on_http_429="retry")
    report = audit_study(study)
    assert report["audit_status"] == "inconsistent"
    assert "rate-limit protocol mismatch" in report["errors"]


def test_mutable_summary_does_not_determine_inventory(study):
    core.write_json(study / "status.json", {"enabled_arms": [], "completed_runs": 0})
    core.write_json(study / "progress.json", {"runs": []})
    assert len(audit_study(study)["per_task"]) == 20


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/outside", "evals/../../outside", "evals\\outside"])
def test_manifest_path_traversal(study, name):
    path = study / "source-manifest.json"
    sources = read(path)
    sources[name] = "0" * 64
    core.write_json(path, sources)
    edit(study / "manifest.json", source_identity=core.digest(sources))
    report = audit_study(study)
    assert report["audit_status"] == "inconsistent"
    assert any("unsafe" in error for error in report["errors"])


def test_duplicate_json_keys_fail_closed(study):
    path = study / "readiness.json"
    path.write_text('{"primary":true,"primary":false,"secondary":true}', encoding="utf-8")
    assert audit_study(study)["audit_status"] == "inconsistent"


@pytest.mark.parametrize("label", ["primary", "secondary"])
def test_missing_preflight_is_incomplete_not_failed_readiness(study, label):
    (study / "preflight" / label / "reply.json").unlink()
    report = audit_study(study)
    assert report["audit_status"] == "incomplete", report["errors"]
    assert report["all_in"] is None


def test_json_overflow_cannot_create_infinite_recorded_time(study):
    path = next((study / "runs").glob("*/single_primary/result.json"))
    value = read(path)
    value["elapsed_seconds"] = "INJECT"
    path.write_text(json.dumps(value).replace('"INJECT"', "1e999"), encoding="utf-8")
    assert audit_study(study)["audit_status"] == "inconsistent"


def test_final_selection_is_not_oracle_corrected(study):
    directory = next((study / "runs").glob("*/resample_primary"))
    case = next(c for c in generate_cases(123, 4) if c.id == directory.parent.name)
    # Two wrong votes beat the one correct vote; no grader feedback may select gold.
    answers = ["999991", case.expected, "999991", "999992"]
    for index, answer in enumerate(answers):
        path = directory / f"call-{index:02d}/reply.json"
        value = read(path)
        body = json.loads(value["output_text"])
        body["output"][1]["content"][0]["text"] = core.wire({"answer": answer, "explanation": "Fixture"})
        value["output_text"] = core.wire(body)
        reply = Reply(**{field.name: value[field.name] for field in fields(Reply)
                         if field.name != "body"}, body=body)
        value["measurement"] = core.recount(reply)
        core.write_json(path, value)
    edit(directory / "result.json", answer=answers[0], stage_answers=answers)
    report = audit_study(study)
    assert report["audit_status"] == "consistent", report["errors"]
    assert report["by_arm"]["resample_primary"]["correct"] == 3
    edit(directory / "result.json", answer=case.expected)
    assert audit_study(study)["audit_status"] == "inconsistent"
