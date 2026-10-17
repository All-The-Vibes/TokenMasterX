"""Offline consistency checking, not authentication or population qualification.

Frozen Python is hashed, never executed. Replay uses the installed implementation
only after checking that its protocol sources match the frozen sources.
"""
from dataclasses import asdict, fields
import hashlib
import math
from pathlib import Path, PurePosixPath
import random

from refinement import core
from refinement.cases import generate_cases, grade_answer
from quality.responses import Reply, parse_json
from refinement.messages import message_reason


class _Missing(ValueError):
    pass


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _sum(values):
    return None if any(value is None for value in values) else sum(values)


def _aggregate(rows):
    result = {key: _sum([row[key] for row in rows]) for key in (
        "tasks", "correct", "calls", "reference_tokens", "visible_tokens",
        "bridge_reported_tokens", "wall_seconds")}
    models = sorted({model for row in rows for model in row["bridge_by_model"]})
    result["bridge_by_model"] = {
        model: {key: _sum([row["bridge_by_model"][model][key] for row in rows
                          if model in row["bridge_by_model"]])
                for key in ("input_tokens", "output_tokens", "total_tokens")} for model in models}
    result["tokens_per_correct"] = (result["reference_tokens"] / result["correct"]
                                    if result["correct"] and result["reference_tokens"] is not None else None)
    return result


class _Audit:
    def __init__(self, output):
        self.root = Path(output).resolve()
        self.errors, self.incomplete, self.bad = [], False, False
        self.allowed = set()
        self.response_ids = set()
        self.rate_limited = False
        self.spent = _aggregate([])
        self.recorded_seconds = 0.0

    def issue(self, message, missing=False):
        self.errors.append(message)
        self.incomplete |= missing
        self.bad |= not missing

    def path(self, name):
        if (type(name) is not str or "\\" in name or ":" in name
                or PurePosixPath(name).is_absolute()
                or any(part in ("", ".", "..") for part in name.split("/"))):
            raise ValueError("unsafe relative path")
        path = self.root / name
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("path escapes study")
        if any(p.is_symlink() for p in (path, *path.parents) if p != self.root and self.root in p.parents):
            raise ValueError("symlink in study")
        return path

    def raw(self, name):
        path = self.path(name)
        if not path.exists():
            raise _Missing(f"missing {name}")
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError(f"oversized {name}")
        return path.read_bytes()

    def read(self, name):
        return parse_json(self.raw(name).decode("utf-8"))

    def check(self, condition, message):
        if not condition:
            raise ValueError(message)

    def call(self, directory, stage, model, request, maximum):
        start_name, reply_name = directory + "/started.json", directory + "/reply.json"
        self.allowed.update((start_name, reply_name))
        started = self.read(start_name)
        api = self.manifest["transports"][model]
        expected_model = self.manifest["expected_reported_models"][model]
        planned = core.wire(core.make_client(self.manifest["base_url"], model, api,
                                             expected_model=expected_model,
                                             max_output_tokens=maximum).request(request))
        self.check(started == dict(stage=stage, model_requested=model, api=api, planned_request=planned,
                                   planned_request_sha256=_sha(planned.encode("utf-8"))),
                   f"{directory}: planned request mismatch")
        self.check(len(planned.encode("utf-8")) <= self.limits.max_request_bytes,
                   f"{directory}: request byte limit exceeded")
        if stage != "readiness":
            self.check(core.tokens.count_tokens(planned) <= self.limits.max_input_reference_tokens,
                       f"{directory}: input reference limit exceeded")
        record = self.read(reply_name)
        self.check(record["stage"] == stage and record["model_requested"] == model and record["api"] == api,
                   f"{directory}: stage/model mismatch")
        data = {field.name: record[field.name] for field in fields(Reply) if field.name != "body"}
        self.check(type(data["ok"]) is bool and type(data["complete"]) is bool
                   and type(data["reason"]) is str, f"{directory}: invalid reply flags")
        self.check(data["input_text"] is None or data["input_text"] == planned,
                   f"{directory}: raw input differs from planned bytes")
        self.check(type(data["elapsed_seconds"]) in (int, float)
                   and math.isfinite(data["elapsed_seconds"]) and data["elapsed_seconds"] >= 0,
                   f"{directory}: invalid recorded call time")
        body, reason = None, data["reason"]
        if data["complete"]:
            self.check(type(data["output_text"]) is str, f"{directory}: complete capture without body")
            self.check(len(data["output_text"].encode("utf-8")) <= self.limits.max_response_bytes,
                       f"{directory}: response byte limit exceeded")
            if data["http_status"] != 200:
                reason = "http_error"
            else:
                try:
                    body = parse_json(data["output_text"])
                    if api == "messages":
                        reason = message_reason(body, expected_model)
                    elif type(body) is not dict or body.get("object") != "response":
                        reason = "invalid_response"
                    elif body.get("model") != model:
                        reason = "model_mismatch"
                    elif body.get("status") != "completed" or type(body.get("output")) is not list:
                        reason = "incomplete_model_response"
                    else:
                        reason = "ok"
                except (ValueError, TypeError, RecursionError):
                    reason = "invalid_response"
            self.check(data["reason"] == reason and data["ok"] == (reason == "ok"),
                       f"{directory}: response model/envelope disagrees with recorded outcome")
        else:
            self.check(not data["ok"], f"{directory}: incomplete successful response")
            self.issue(f"{directory}: incomplete raw response", missing=True)
        if data["input_text"] is None:
            self.issue(f"{directory}: missing raw input", missing=True)
        reply = Reply(**data, body=body)
        measurement = core.recount(reply)
        self.check(record["measurement"] == measurement, f"{directory}: saved measurement mismatch")
        response_id = body.get("id") if reply.ok else None
        if type(response_id) is str and response_id:
            self.check(response_id not in self.response_ids, f"{directory}: duplicate successful response id")
            self.response_ids.add(response_id)
        self.rate_limited |= reply.http_status == 429
        return reply, measurement, model

    def row(self, calls, tasks=0, correct=0, wall=0):
        models = {}
        for reply, measurement, requested in calls:
            reported = measurement["reported_model"]
            model = reported if type(reported) is str and reported else requested
            usage = measurement["bridge_usage"]
            entry = models.setdefault(model, {key: [] for key in ("input_tokens", "output_tokens", "total_tokens")})
            for key in entry:
                entry[key].append(usage[key] if usage else None)
        return dict(tasks=tasks, correct=correct, calls=len(calls),
                    reference_tokens=_sum([m["reference_total"] for _, m, _ in calls]),
                    visible_tokens=_sum([m["visible_total"] for _, m, _ in calls]),
                    bridge_reported_tokens=_sum([m["bridge_usage"]["total_tokens"]
                                                 if m["bridge_usage"] else None for _, m, _ in calls]),
                    wall_seconds=wall, bridge_by_model={
                        model: {key: _sum(values) for key, values in entry.items()}
                        for model, entry in models.items()})

    def frozen(self):
        self.manifest = m = self.read("manifest.json")
        sources = self.read("source-manifest.json")
        self.check(type(sources) is dict and sources, "invalid source manifest")
        self.check(core.digest(sources) == m["source_identity"], "source manifest identity mismatch")
        for name, expected in sources.items():
            self.path(name)  # reject traversal before prefixing a manifest-controlled path
            self.check(_sha(self.raw("source/token-master-plugin/" + name)) == expected,
                       f"source hash mismatch: {name}")
        required = ["evals/run_refinement.py", "evals/refinement/core.py", "evals/refinement/cases.py",
                    "evals/refinement/audit.py", "evals/refinement/__init__.py",
                    "evals/refinement/messages.py",
                    "evals/quality/responses.py", "evals/quality/measurement.py", "evals/quality/__init__.py",
                    "skills/token-master/brainspace/tokens.py", "skills/token-master/brainspace/__init__.py"]
        for name in required:
            self.check(name in sources and _sha((core.PLUGIN / name).read_bytes()) == sources[name],
                       f"unsupported or missing frozen protocol source: {name}")
        self.check(_sha(self.raw("cl100k_base.tiktoken")) == core.tokens.VOCABULARY_SHA256,
                   "frozen tokenizer hash mismatch")
        backend = core.tokens.backend_info()
        self.check(backend["exact_reference"], "offline tokenizer unavailable")
        self.check(core.wire(m["tokenizer"]) == core.wire(backend), "tokenizer metadata mismatch")
        self.check(_sha(self.raw("cases.json")) == m["cases_sha256"], "cases hash mismatch")
        self.cases = generate_cases(m["seed"], m["tasks"])
        self.check(self.read("cases.json") == [dict(asdict(c), identity=c.identity) for c in self.cases],
                   "regenerated case identity mismatch")
        self.check(type(m["transports"]) is dict and set(m["transports"]) == {m["primary"], m["secondary"]}
                   and m["transports"][m["primary"]] == "responses"
                   and m["transports"][m["secondary"]] in ("responses", "messages"), "invalid transport mapping")
        reported = m["secondary_reported_model_override"]
        self.check(reported is None or type(reported) is str and reported.strip(), "invalid reported model override")
        self.check(m["expected_reported_models"] == {
            m["primary"]: m["primary"], m["secondary"]: reported or m["secondary"]},
            "reported model mapping mismatch")
        all_policies = core.arms(m["primary"], m["secondary"], m["transports"][m["secondary"]], reported)
        selected = m["selected_arms"]
        self.check(type(selected) is list and selected and len(set(selected)) == len(selected)
                   and not set(selected) - {arm.name for arm in all_policies}, "invalid arm selection")
        self.policies = [arm for arm in all_policies if arm.name in selected]
        self.check(selected == [arm.name for arm in self.policies], "arm selection order mismatch")
        self.check(m["schema_version"] == 1 and m["protocol"] == core.PROTOCOL, "unsupported protocol")
        self.check(m["arms"] == [dict(asdict(a), identity=a.identity) for a in self.policies],
                   "arm identity mismatch")
        schedule = [[c.id, a.name] for c in self.cases for a in self.policies]
        random.Random(m["seed"] ^ 0x51A7).shuffle(schedule)
        self.check(m["schedule"] == schedule, "schedule mismatch")
        self.limits = core.Limits(**m["limits"])
        self.check(m["maximum_attempts"] == 2 + len(self.cases) * sum(len(a.schedule()) for a in self.policies),
                   "maximum attempts mismatch")
        for name, maximum in (("maximum_study_seconds", 3600), ("observed_reference_stop_threshold", 10_000_000)):
            self.check(type(m[name]) in (int, float) and 0 < m[name] <= maximum, f"invalid {name}")
        from run_refinement import READINESS
        self.check(m["preflight"] == dict(request=READINESS, max_output_tokens=128, attempts_per_model=1),
                   "readiness protocol mismatch")
        self.check(m["unavailable_secondary_policy"] == "run-primary-only-controls-no-substitution",
                   "fallback protocol mismatch")
        self.check(m["on_http_429"] == "stop-study-no-retry", "rate-limit protocol mismatch")

    def preflight(self):
        ready, calls, missing = {}, [], False
        for label in ("primary", "secondary"):
            try:
                call = self.call("preflight/" + label, "readiness", self.manifest[label],
                                 self.manifest["preflight"]["request"], 128)
                calls.append(call)
                try:
                    ready[label] = call[0].ok and core.visible_text(call[0].body).strip() == "READY"
                except (ValueError, TypeError, KeyError):
                    ready[label] = False
            except _Missing as error:
                self.issue(str(error), missing=True)
                ready[label], missing = False, True
            if label == "primary" and not ready[label]:
                break
        saved = self.read("readiness.json")
        if missing:
            raise _Missing("readiness cannot be reconstructed from missing captures")
        self.check(saved == ready and all(type(v) is bool for v in saved.values()), "readiness summary mismatch")
        row = self.row(calls, wall=sum(call[0].elapsed_seconds for call in calls))
        if len(calls) != len(ready):
            for key in ("calls", "reference_tokens", "visible_tokens", "bridge_reported_tokens", "wall_seconds"):
                row[key] = None
        return ready, row

    def task(self, case, arm):
        directory = f"runs/{case.id}/{arm.name}"
        self.allowed.add(directory + "/result.json")
        outputs, calls, stop, missing = [], [], "completed", False
        try:
            result = self.read(directory + "/result.json")
        except _Missing as error:
            self.issue(str(error), missing=True)
            result, missing = None, True
        for index, (stage, model) in enumerate(arm.schedule()):
            name = f"{directory}/call-{index:02d}"
            if not self.path(name).exists():
                if result is None or result["attempts"] > index or result["status"] == "completed":
                    self.issue(f"missing {name}", missing=True)
                    missing = True
                else:
                    stop = result["status"]
                    planned = core.wire(core.make_client(
                        self.manifest["base_url"], model, self.manifest["transports"][model],
                        expected_model=self.manifest["expected_reported_models"][model],
                        max_output_tokens=self.limits.max_output_tokens).request(
                            core.payload(case.prompt, stage, outputs)))
                    if stop == "input_bound":
                        self.check(len(planned.encode("utf-8")) > self.limits.max_request_bytes
                                   or core.tokens.count_tokens(planned) > self.limits.max_input_reference_tokens,
                                   f"{directory}: unsupported input_bound")
                    elif stop == "policy_deadline":
                        self.check(result["elapsed_seconds"] >= self.limits.policy_seconds,
                                   f"{directory}: unsupported policy_deadline")
                    elif stop == "study_limit":
                        spent = _aggregate([self.spent, self.row(calls)])
                        if not (self.rate_limited or spent["calls"] is None
                                or spent["calls"] >= self.manifest["maximum_attempts"]
                                or spent["reference_tokens"] is None
                                or spent["reference_tokens"] + core.tokens.count_tokens(planned) >
                                self.manifest["observed_reference_stop_threshold"]
                                or self.recorded_seconds + result["elapsed_seconds"] >= self.manifest["maximum_study_seconds"]):
                            self.issue(f"{directory}: study deadline lacks whole-study timing evidence", missing=True)
                    else:
                        self.check(False, f"{directory}: unsupported early stop")
                break
            try:
                call = self.call(name, stage, model, core.payload(case.prompt, stage, outputs),
                                 self.limits.max_output_tokens)
            except _Missing as error:
                self.issue(str(error), missing=True)
                missing = True
                break
            calls.append(call)
            reply, measurement, _ = call
            if not reply.ok:
                stop = reply.reason
                break
            if measurement["bridge_usage"] and measurement["bridge_usage"]["output_tokens"] > self.limits.max_output_tokens:
                stop = "reported_output_limit_exceeded"
                break
            try:
                outputs.append(core.decode_stage(reply.body, stage))
            except (ValueError, TypeError, KeyError, RecursionError):
                stop = "invalid_stage_output"
                break
        answer = core.select_answer(arm, outputs) if stop == "completed" and not missing else None
        if result is not None:
            self.check(type(result["elapsed_seconds"]) in (int, float)
                       and math.isfinite(result["elapsed_seconds"]) and result["elapsed_seconds"] >= 0,
                       f"{directory}: invalid recorded task time")
            self.check(result["protocol"] == core.PROTOCOL and result["arm"] == asdict(arm)
                       and result["policy_id"] == arm.identity, f"{directory}: result identity mismatch")
            if not missing:
                self.check(all(result[key] == value for key, value in dict(
                    status=stop, answer=answer, attempts=len(calls),
                    stage_answers=[o["answer"] for o in outputs]).items()), f"{directory}: result outcome mismatch")
        row = self.row(calls, tasks=1, correct=int(grade_answer(case, answer)) if not missing else None,
                       wall=result["elapsed_seconds"] if result else None)
        if missing:
            for key in ("calls", "reference_tokens", "visible_tokens", "bridge_reported_tokens"):
                row[key] = None
            for model in {model for _, model in arm.schedule()}:
                row["bridge_by_model"][model] = dict(input_tokens=None, output_tokens=None, total_tokens=None)
        return dict(row, case_id=case.id, arm=arm.name, status=stop if not missing else "incomplete",
                    answer=answer, stage_answers=[o["answer"] for o in outputs])


def audit_study(output: Path) -> dict:
    """Audit local evidence without network calls, code execution, or oracle selection."""
    audit, rows, overhead = _Audit(output), [], None
    try:
        audit.frozen()
        ready, overhead = audit.preflight()
        enabled = {a.name: a for a in audit.policies if ready.get("primary") and (
            ready.get("secondary") or a.writer == a.critic == audit.manifest["primary"])}
        cases = {c.id: c for c in audit.cases}
        audit.spent, audit.recorded_seconds = overhead, overhead["wall_seconds"] or 0
        for case_id, name in audit.manifest["schedule"]:
            if name in enabled:
                row = audit.task(cases[case_id], enabled[name])
                rows.append(row)
                audit.spent = _aggregate([overhead, *rows])
                audit.recorded_seconds += row["wall_seconds"] or 0
        for root in ("runs", "preflight"):
            for path in audit.path(root).rglob("*"):
                if path.is_file() and path.relative_to(audit.root).as_posix() not in audit.allowed:
                    audit.issue(f"unexpected capture/result: {path.relative_to(audit.root).as_posix()}")
    except (_Missing, OSError) as error:
        audit.issue(str(error), missing=True)
    except (ValueError, TypeError, KeyError, IndexError, RecursionError, AttributeError, OverflowError) as error:
        audit.issue(str(error))
    by_arm = {name: _aggregate([r for r in rows if r["arm"] == name]) for name in sorted({r["arm"] for r in rows})}
    return dict(audit_status="inconsistent" if audit.bad else "incomplete" if audit.incomplete else "consistent",
                errors=audit.errors, by_arm=by_arm, per_task=rows, preflight=overhead,
                all_in=_aggregate([overhead, *rows]) if overhead else None, population_certificate=False,
                weights_provider_independently_authenticated=False,
                bridge_reported_tokens_basis="heterogeneous bridge raw sum; not comparable model compute",
                wall_seconds_basis="recorded task stopwatches plus recorded preflight calls; not independently timed",
                scope="Internal capture consistency only; no proof, confidence interval, or policy promotion. "
                      "Response IDs are unauthenticated; absent IDs cannot be checked for duplicate captures.")
