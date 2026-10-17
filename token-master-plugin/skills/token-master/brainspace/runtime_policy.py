"""Closed controller policy union; data only, no execution or resource discovery.

RequestPolicy JSON/identity and legacy neighbor ordering are untouched. The new
RuntimePolicy binds supported component pins and execution semantics, not asset
availability, implementation-file hashes, model quality, or hidden computation.
Those belong to explicit resources, the frozen regime and independent evidence.

True off is the default. Inactive settings reject rather than silently normalize
caller input. Neighbor generation alone derives the settings required by a
single conceptual component switch. No paths, code, credentials or plugins.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
import hashlib
import json
from typing import TypeAlias, overload

from .headroom import COMMIT as HEADROOM_COMMIT, IMAGE_ID as HEADROOM_IMAGE_ID
from .headroom import MODEL_REVISION as HEADROOM_MODEL_REVISION
from .headroom_worker import MODEL_SHA256 as HEADROOM_MODEL_SHA256
from .headroom_worker import TOKENIZER_REVISION as HEADROOM_TOKENIZER_REVISION
from .ponytail import PINNED_INSTRUCTIONS_SHA256, PINNED_SOURCE_COMMIT
from .request_policy import RequestPolicy, policy_neighbors
from .runtime_io import parse_json


VERSION = "runtime-policy-v1"
EXECUTION_CONTRACT = "runtime-execution-v1"
MAX_CONTROLLER_NEIGHBORS = 12
MAX_POLICY_JSON_BYTES = 65536
_LEGACY_VERSIONS = ("request-policy-v1", "request-policy-v2", "request-policy-v3")
_REQUEST_VERSIONS = (*_LEGACY_VERSIONS, "request-policy-v4")
_BACKENDS = ("none", "local", "headroom")
_BUDGETS = (None, *range(1, 61))
_HEADROOM_STRATEGIES = ("upstream-default-v1", "native-documents-v1",
                       "native-documents-structure-tags-v1")
_HEADROOM_ROOT_REFERENCE_STYLES = ("annotated-v1", "compact-root-v1")
_HEADROOM_STRUCTURE_GUARDS = ("none", "document-structure-v1")


def _off_request() -> RequestPolicy:
    return RequestPolicy(version="request-policy-v3", enabled=False)


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """One pinned composition. No fake enabled property or automatic promotion.

The nested policy holds local planner or Headroom protection settings and fixed
wire caps. It is enabled exactly for the local backend. For backend none its
unused tuning/version must be the canonical disabled V3 defaults; explicitly
declared caps remain valid and never change during neighborhood search.

Pins always describe the supported component set, even for inactive components.
``headroom_time_budget_seconds=None`` means upstream default, not infinite time
or a hard deadline guarantee. Positive values are cooperative budgets.
``native-documents-v1`` is an explicit guarded Headroom strategy, never a
default. The upstream-default strategy is omitted from serialization to retain
every previously stored policy identity.
Compact root references are separately opt-in and require guarded Headroom.
The default annotated style is likewise omitted from serialized policies.
    """

    version: str = VERSION
    execution_contract: str = EXECUTION_CONTRACT
    backend: str = "none"
    request_policy: RequestPolicy = field(default_factory=_off_request)
    instruction: str = "none"
    require_nonexpanding_input: bool = False
    headroom_time_budget_seconds: int | None = None
    ponytail_source_commit: str = PINNED_SOURCE_COMMIT
    ponytail_instructions_sha256: str = PINNED_INSTRUCTIONS_SHA256
    headroom_image_id: str = HEADROOM_IMAGE_ID
    headroom_source_commit: str = HEADROOM_COMMIT
    headroom_model_revision: str = HEADROOM_MODEL_REVISION
    headroom_model_sha256: str = HEADROOM_MODEL_SHA256
    headroom_tokenizer_revision: str = HEADROOM_TOKENIZER_REVISION
    headroom_strategy: str = "upstream-default-v1"
    headroom_root_reference_style: str = "annotated-v1"
    headroom_structure_guard: str = "none"

    def __post_init__(self) -> None:
        expected = {
            "version": VERSION, "execution_contract": EXECUTION_CONTRACT,
            "ponytail_source_commit": PINNED_SOURCE_COMMIT,
            "ponytail_instructions_sha256": PINNED_INSTRUCTIONS_SHA256,
            "headroom_image_id": HEADROOM_IMAGE_ID, "headroom_source_commit": HEADROOM_COMMIT,
            "headroom_model_revision": HEADROOM_MODEL_REVISION,
            "headroom_model_sha256": HEADROOM_MODEL_SHA256,
            "headroom_tokenizer_revision": HEADROOM_TOKENIZER_REVISION,
        }
        if any(type(getattr(self, name)) is not str or getattr(self, name) != pin
               for name, pin in expected.items()):
            raise ValueError("runtime_policy_pin_or_contract_mismatch")
        if (type(self.backend) is not str or self.backend not in _BACKENDS
                or type(self.instruction) is not str or self.instruction not in ("none", "ponytail")
                or type(self.require_nonexpanding_input) is not bool):
            raise ValueError("invalid_runtime_policy_selection")
        if type(self.request_policy) is not RequestPolicy:
            raise ValueError("typed_request_policy_required")
        self.request_policy.__post_init__()
        if self.request_policy.enabled is not (self.backend == "local"):
            raise ValueError("runtime_policy_reducer_conflict")
        if self.backend != "local" and self.request_policy.version != "request-policy-v3":
            raise ValueError("inactive_request_version")
        if self.request_policy.version == "request-policy-v4" and not self.require_nonexpanding_input:
            raise ValueError("v4_requires_nonexpanding_input")
        budget = self.headroom_time_budget_seconds
        if budget is not None and (type(budget) is not int or not 1 <= budget <= 60):
            raise ValueError("invalid_headroom_time_budget_seconds")
        if self.backend != "headroom" and budget is not None:
            raise ValueError("inactive_headroom_budget")
        if type(self.headroom_strategy) is not str or self.headroom_strategy not in _HEADROOM_STRATEGIES:
            raise ValueError("invalid_headroom_strategy")
        if self.headroom_strategy != "upstream-default-v1":
            if self.backend != "headroom":
                raise ValueError("inactive_headroom_strategy")
            if not self.require_nonexpanding_input:
                raise ValueError("headroom_documents_require_nonexpanding_input")
        if (type(self.headroom_root_reference_style) is not str
                or self.headroom_root_reference_style not in _HEADROOM_ROOT_REFERENCE_STYLES):
            raise ValueError("invalid_headroom_root_reference_style")
        if self.headroom_root_reference_style != "annotated-v1":
            if self.backend != "headroom":
                raise ValueError("inactive_headroom_root_reference_style")
            if not self.require_nonexpanding_input:
                raise ValueError("compact_root_requires_nonexpanding_input")
        if (type(self.headroom_structure_guard) is not str
                or self.headroom_structure_guard not in _HEADROOM_STRUCTURE_GUARDS):
            raise ValueError("invalid_headroom_structure_guard")
        if self.headroom_structure_guard != "none" and (
                self.backend != "headroom" or self.headroom_strategy not in (
                    "native-documents-v1", "native-documents-structure-tags-v1")
                or not self.require_nonexpanding_input):
            raise ValueError("structure_guard_requires_guarded_documents")
        if (self.headroom_strategy == "native-documents-structure-tags-v1"
                and self.headroom_structure_guard != "document-structure-v1"):
            raise ValueError("preprotection_requires_structure_guard")
        if self.backend == "none":
            canonical = _inactive_request(self.request_policy)
            if self.request_policy != canonical:
                raise ValueError("inactive_request_tuning")
            if self.instruction == "none" and self.require_nonexpanding_input:
                raise ValueError("inactive_composition_guard")

    def to_dict(self) -> dict:
        self.__post_init__()
        value = {f.name: self.request_policy.to_dict() if f.name == "request_policy"
                 else getattr(self, f.name) for f in fields(self)}
        if self.headroom_strategy == "upstream-default-v1":
            del value["headroom_strategy"]
        if self.headroom_root_reference_style == "annotated-v1":
            del value["headroom_root_reference_style"]
        if self.headroom_structure_guard == "none":
            del value["headroom_structure_guard"]
        return value

    @classmethod
    def from_dict(cls, value: dict) -> RuntimePolicy:
        if (type(value) is not dict or value.get("version") != VERSION
                or set(value) - {f.name for f in fields(cls)}):
            raise ValueError("invalid_runtime_policy_fields")
        values = dict(value)
        if "request_policy" in values:
            if type(values["request_policy"]) is not dict:
                raise ValueError("request_policy_object_required")
            values["request_policy"] = RequestPolicy.from_dict(values["request_policy"])
        return cls(**values)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)

    @classmethod
    def from_json(cls, text: str) -> RuntimePolicy:
        return cls.from_dict(_parse_policy(text))

    @property
    def policy_id(self) -> str:
        return VERSION + ":" + hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


ControllerPolicy: TypeAlias = RequestPolicy | RuntimePolicy


def _parse_policy(text: str) -> dict:
    if type(text) is not str or len(text.encode("utf-8")) > MAX_POLICY_JSON_BYTES:
        raise ValueError("bounded_policy_json_required")
    value = parse_json(text)
    if type(value) is not dict:
        raise ValueError("policy_object_required")
    return value


def decode_policy(text: str) -> ControllerPolicy:
    """Dispatch only known tags; never wrap/reserialize legacy policy storage."""
    value = _parse_policy(text)
    if value.get("version") in _REQUEST_VERSIONS:
        return RequestPolicy.from_json(text)
    if value.get("version") == VERSION:
        return RuntimePolicy.from_dict(value)
    raise ValueError("unsupported_controller_policy_version")


def _validate(policy: ControllerPolicy) -> None:
    if type(policy) not in (RequestPolicy, RuntimePolicy):
        raise ValueError("unsupported_controller_policy_type")
    policy.__post_init__()


def baseline_policy_admissible(policy: ControllerPolicy) -> bool:
    """Structural admission only. True never attests model quality or resources."""
    try:
        _validate(policy)
    except (TypeError, ValueError):
        return False
    if type(policy) is RuntimePolicy:
        return True
    assert isinstance(policy, RequestPolicy)
    return policy.enabled is True


def _inactive_request(policy: RequestPolicy) -> RequestPolicy:
    return replace(_off_request(), max_input_tokens=policy.max_input_tokens,
                   max_wire_bytes=policy.max_wire_bytes, max_output_tokens=policy.max_output_tokens)


def _switch_backend(policy: RuntimePolicy, backend: str) -> RuntimePolicy:
    nested = (_inactive_request(policy.request_policy) if backend == "none"
              else replace(policy.request_policy, enabled=backend == "local",
                           version=policy.request_policy.version if backend == "local" else "request-policy-v3"))
    return replace(
        policy, backend=backend, request_policy=nested,
        headroom_time_budget_seconds=None,
        headroom_strategy="upstream-default-v1",
        headroom_root_reference_style="annotated-v1",
        headroom_structure_guard="none",
        require_nonexpanding_input=policy.require_nonexpanding_input
        if backend != "none" or policy.instruction != "none" else False)


@overload
def controller_policy_neighbors(policy: RequestPolicy) -> tuple[RequestPolicy, ...]: ...


@overload
def controller_policy_neighbors(policy: RuntimePolicy) -> tuple[RuntimePolicy, ...]: ...


def controller_policy_neighbors(policy: ControllerPolicy) -> tuple[ControllerPolicy, ...]:
    """Finite one-component moves; never search pins, caps, gates or authority.

At most 11 local neighbors (2 backend + instruction + guard + 6 local tuning
+ one guarded versioned mode choice),
or 8 Headroom neighbors (2 backend + instruction + guard + 2 adjacent budgets
+ strategy + root style). True off has 6 choices including direct guarded
document strategies with either root style; their required settings are a
single explicit entry choice, not an intermediate-policy promotion.
Runtime tuples are sorted by the closed runtime key; legacy tuples and sort
keys remain exactly as before. No-op IDs and duplicate IDs are excluded.
    """
    _validate(policy)
    if type(policy) is RequestPolicy:
        return policy_neighbors(policy)
    assert isinstance(policy, RuntimePolicy)
    candidates = [_switch_backend(policy, backend) for backend in _BACKENDS if backend != policy.backend]
    instruction = "ponytail" if policy.instruction == "none" else "none"
    candidates.append(replace(
        policy, instruction=instruction,
        require_nonexpanding_input=policy.require_nonexpanding_input
        if policy.backend != "none" or instruction != "none" else False))
    if ((policy.backend != "none" or policy.instruction != "none")
            and policy.request_policy.version != "request-policy-v4"
            and policy.headroom_strategy == "upstream-default-v1"
            and policy.headroom_root_reference_style != "compact-root-v1"):
        candidates.append(replace(policy, require_nonexpanding_input=not policy.require_nonexpanding_input))
    if policy.backend == "none" and policy.instruction == "none":
        document_policy = replace(
            _switch_backend(policy, "headroom"), headroom_strategy="native-documents-v1",
            require_nonexpanding_input=True)
        candidates.extend((document_policy, replace(
            document_policy, headroom_root_reference_style="compact-root-v1")))
    if policy.backend in ("none", "local"):
        # A single versioned mode choice includes the whole-wire guard required
        # by V4; true off need not first promote legacy local V3 to reach it.
        version = ("request-policy-v3" if policy.request_policy.version == "request-policy-v4"
                   else "request-policy-v4")
        candidates.append(replace(
            policy, backend="local", request_policy=replace(
                policy.request_policy, version=version, enabled=True),
            require_nonexpanding_input=True))
    if policy.backend == "local":
        candidates.extend(replace(policy, request_policy=nested) for nested in policy_neighbors(policy.request_policy))
    elif policy.backend == "headroom":
        root_style = ("compact-root-v1" if policy.headroom_root_reference_style == "annotated-v1"
                      else "annotated-v1")
        candidates.append(replace(
            policy, headroom_root_reference_style=root_style,
            require_nonexpanding_input=True if root_style == "compact-root-v1"
            else policy.require_nonexpanding_input))
        strategy = ("native-documents-v1" if policy.headroom_strategy == "upstream-default-v1"
                    else "upstream-default-v1")
        candidates.append(replace(
            policy, headroom_strategy=strategy,
            headroom_structure_guard=policy.headroom_structure_guard
            if strategy == "native-documents-v1" else "none",
            require_nonexpanding_input=True if strategy == "native-documents-v1"
            else policy.require_nonexpanding_input))
        index = _BUDGETS.index(policy.headroom_time_budget_seconds)
        for adjacent in (index - 1, index + 1):
            if 0 <= adjacent < len(_BUDGETS):
                candidates.append(replace(policy, headroom_time_budget_seconds=_BUDGETS[adjacent]))
    unique = {item.policy_id: item for item in candidates if item.policy_id != policy.policy_id}
    if len(unique) > MAX_CONTROLLER_NEIGHBORS:
        raise ValueError("runtime_policy_neighborhood_exceeded")
    return tuple(sorted(unique.values(), key=controller_policy_sort_key))


def controller_policy_sort_key(policy: ControllerPolicy) -> tuple[int | str, ...]:
    """Keep the legacy optimizer's exact four-element ordering key."""
    _validate(policy)
    if type(policy) is RequestPolicy:
        return (policy.min_tool_chars, policy.keep_recent_tool_results,
                -policy.max_transforms, policy.policy_id)
    assert isinstance(policy, RuntimePolicy)
    nested = policy.request_policy
    return (_BACKENDS.index(policy.backend), int(policy.instruction == "ponytail"),
            int(policy.require_nonexpanding_input), _BUDGETS.index(policy.headroom_time_budget_seconds),
            nested.min_tool_chars, nested.keep_recent_tool_results, -nested.max_transforms, policy.policy_id)
