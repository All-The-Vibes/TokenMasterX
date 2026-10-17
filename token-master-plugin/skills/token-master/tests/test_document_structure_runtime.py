"""Manual explicit structure guard through the real runtime; no native/inference."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from brainspace.runtime_policy import RuntimePolicy, controller_policy_neighbors
from test_headroom_document_runtime import Transport, request
import test_headroom_document_runtime as document_fixtures


document_setup = document_fixtures.setup


FIELD = "headroom_structure_guard"
GUARD = "document-structure-v1"
TABLE = "| Resource | Path |\n|---|---|\n| Catalog | `/srv/models.json` |\n"
ORDERED = "1. Config path first.\n2. Workspace path second.\n"
PROSE = ("General deployment documentation and operational background. " * 70) + "\n\n"


def guarded_policy(**changes):
    return RuntimePolicy(**{
        "backend": "headroom", "headroom_strategy": "native-documents-v1",
        "require_nonexpanding_input": True, FIELD: GUARD, **changes,
    })


def test_guard_is_default_omitted_closed_and_identity_bound():
    legacy = RuntimePolicy(
        backend="headroom", headroom_strategy="native-documents-v1",
        require_nonexpanding_input=True,
    )
    assert getattr(legacy, FIELD) == "none"
    assert FIELD not in legacy.to_dict()
    assert RuntimePolicy.from_dict({**legacy.to_dict(), FIELD: "none"}) == legacy
    policy = guarded_policy()
    assert policy.policy_id != legacy.policy_id
    assert RuntimePolicy.from_json(policy.to_json()) == policy
    assert all(isinstance(item, RuntimePolicy) for item in controller_policy_neighbors(policy))
    assert all(getattr(item, FIELD) == "none" for item in controller_policy_neighbors(RuntimePolicy()))


@pytest.mark.parametrize("changes", [
    {FIELD: True}, {FIELD: None}, {FIELD: "future-unknown"}, {"backend": "none"},
    {"headroom_strategy": "upstream-default-v1"}, {"require_nonexpanding_input": False},
])
def test_unsupported_or_inactive_guard_cannot_be_selected(changes):
    with pytest.raises(ValueError):
        guarded_policy(**changes)


@pytest.fixture
def guarded(document_setup):
    old, state = document_setup
    from brainspace.runtime import RuntimeSession
    # The existing fixture replaces only the worker/resource boundary. Create
    # an actual separate runtime using the new typed policy, not mutable fields.
    value = RuntimeSession(
        workspace=old.workspace, output=old.output.parent / "guarded-runtime",
        session_id="structure-guard", transport=Transport(),
        runtime_policy=guarded_policy(headroom_root_reference_style="compact-root-v1"),
        runtime_resources=old.runtime_resources,
    )
    yield value, state
    value.close()


@pytest.mark.parametrize("kind", ["table", "order", "duplicated", "reordered", "unsupported"])
def test_changed_data_structure_is_rejected_without_root_or_new_call(guarded, kind):
    session, state = guarded
    blocks = TABLE + "\n" + ORDERED
    source = PROSE + blocks
    replacement = {
        "table": TABLE.replace("`/srv/models.json`", "`/other/models.json`") + "\n" + ORDERED,
        "order": TABLE + "\n" + ORDERED.replace("1.", "2.").replace("second.", "first."),
        "duplicated": blocks + "\n" + TABLE,
        "reordered": ORDERED + "\n" + TABLE,
        "unsupported": "> " + TABLE,
    }[kind]
    state["replacement"] = replacement
    payload = request(session, content=source)
    before = deepcopy(payload)
    session.invoke(payload, intent="overview")
    emitted = json.loads(session.transport.sent[-1])
    assert emitted == before
    assert len(session.transport.sent) == 1
    assert session.ccr.stats()["entries"] == 0
    preparation = json.loads((session.output / "preparations.jsonl").read_text("utf-8"))
    assert preparation["changed_messages"] == []
    assert preparation["input_composition"]["projection_reason"] == "headroom_structure_guard_reversion"


def test_intact_structures_allow_shorter_prose_and_exact_root(guarded):
    session, state = guarded
    blocks = TABLE + "\n" + ORDERED
    source = PROSE + blocks
    state["replacement"] = "Shorter background.\n\n" + blocks
    payload = request(session, content=source)
    session.invoke(payload, intent="overview")
    emitted = json.loads(session.transport.sent[-1])
    projected = emitted["messages"][3]["content"]
    reference, content = projected.split("\n", 1)
    assert content == state["replacement"] and content != source
    assert session.ccr.retrieve(reference) == source
    assert emitted["messages"][-1] == payload["messages"][-1]
    assert emitted["messages"][0] == payload["messages"][0]
    assert session.profile[FIELD] == GUARD
    with pytest.raises(AttributeError):
        session._headroom_structure_guard = "none"


def test_default_policy_does_not_silently_change_old_qualification(document_setup):
    session, state = document_setup
    assert session.runtime_policy.headroom_structure_guard == "none"
    assert FIELD not in session.profile
    source = PROSE + TABLE + "\n" + ORDERED
    state["replacement"] = "Legacy lossy view."
    session.invoke(request(session, content=source), intent="overview")
    emitted = json.loads(session.transport.sent[-1])
    assert emitted["messages"][3]["content"].endswith("Legacy lossy view.")


def test_explicit_guard_deactivates_only_with_backend_or_strategy_switch():
    policy = guarded_policy()
    neighbors = controller_policy_neighbors(policy)
    assert neighbors
    for item in neighbors:
        if item.backend != "headroom" or item.headroom_strategy != "native-documents-v1":
            assert getattr(item, FIELD) == "none"
        else:
            assert getattr(item, FIELD) == GUARD
        item.__post_init__()
    assert replace(policy, instruction="ponytail").headroom_structure_guard == GUARD
