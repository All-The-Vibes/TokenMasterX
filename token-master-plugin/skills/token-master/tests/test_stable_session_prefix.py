"""Copilot CLI's per-session folder line moves out of the system prompt, so sessions share a cached prefix."""
from copy import deepcopy
import json

from brainspace.native_transport import NativeResponsesTransport, SESSION_FOLDER_MOVED, stable_session_prefix

SYSTEM = "You are a coding agent.\n<session_context>\nSession folder: {folder}\n\nContents:\n- files/\n</session_context>"


def request(folder="C:/Users/dev/.copilot/session-state/abc123", task="Fix the bug.", blocks=False, history=()):
    system = SYSTEM.format(folder=folder)
    if blocks:
        first = {"type": "message", "role": "system", "content": [
            {"type": "input_text", "text": system, "prompt_cache_breakpoint": True}]}
        user = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": task}]}
    else:
        first, user = {"role": "system", "content": system}, {"role": "user", "content": task}
    return {"model": "fixture", "input": [first, user, *deepcopy(list(history))], "store": False}


def text(item):
    content = item["content"]
    return content if isinstance(content, str) else "".join(block["text"] for block in content)


def test_folder_moves_to_the_first_user_message():
    moved = stable_session_prefix(request())
    assert text(moved["input"][0]) == SYSTEM.format(folder="X").replace("Session folder: X", SESSION_FOLDER_MOVED)
    assert text(moved["input"][1]) == "Session folder: C:/Users/dev/.copilot/session-state/abc123\n\nFix the bug."


def test_two_sessions_share_the_system_prompt_bytes():
    a = stable_session_prefix(request("C:/s/session-state/one", "Task one."))
    b = stable_session_prefix(request("C:/s/session-state/two", "Task two."))
    assert json.dumps(a["input"][0]) == json.dumps(b["input"][0])
    assert a["input"][1] != b["input"][1]


def test_every_call_of_a_session_sends_the_same_prefix():
    history = [{"type": "function_call", "call_id": "c1", "name": "view", "arguments": "{}"},
               {"type": "function_call_output", "call_id": "c1", "output": "Session folder: not a system line"}]
    first, later = stable_session_prefix(request()), stable_session_prefix(request(history=history))
    assert later["input"][:2] == first["input"][:2] and later["input"][2:] == history
    assert stable_session_prefix(first) is first  # already moved: unchanged


def test_content_blocks_keep_their_metadata():
    moved = stable_session_prefix(request(blocks=True))
    block = moved["input"][0]["content"][0]
    assert block["prompt_cache_breakpoint"] is True and SESSION_FOLDER_MOVED in block["text"]
    assert moved["input"][1]["content"][0]["text"].startswith("Session folder: C:/Users/dev/")


def test_unchanged_when_ambiguous_or_absent():
    two = request()
    two["input"][0]["content"] += "\nSession folder: C:/x/session-state/other"
    absent = {"model": "fixture", "input": [{"role": "system", "content": "No folder here.\nSession folder: C:/notes"},
                                            {"role": "user", "content": "Hi."}]}
    no_user = {"model": "fixture", "input": [{"role": "system", "content": SYSTEM.format(folder="C:/session-state/y")}]}
    no_text = request()
    no_text["input"][1]["content"] = []
    both = request()
    both["instructions"] = SYSTEM.format(folder="C:/i/session-state/z")
    for body in (two, absent, no_user, no_text, both):
        before = deepcopy(body)
        assert stable_session_prefix(body) is body and body == before


def test_a_line_split_across_blocks_is_moved_whole():
    body = request(blocks=True)
    system = body["input"][0]["content"][0]["text"]
    cut = system.index("session-state") + 3
    body["input"][0]["content"] = [{"type": "input_text", "text": system[:cut]},
                                   {"type": "input_text", "text": system[cut:], "prompt_cache_breakpoint": True}]
    moved = stable_session_prefix(body)
    assert text(moved["input"][0]) == text(stable_session_prefix(request())["input"][0])
    assert moved["input"][0]["content"][1]["prompt_cache_breakpoint"] is True
    assert text(moved["input"][1]) == "Session folder: C:/Users/dev/.copilot/session-state/abc123\n\nFix the bug."


def test_instructions_field_is_moved_too():
    body = {"model": "fixture", "instructions": SYSTEM.format(folder="C:/f/session-state/z"),
            "input": [{"role": "user", "content": "Go."}]}
    moved = stable_session_prefix(body)
    assert SESSION_FOLDER_MOVED in moved["instructions"]
    assert moved["input"][0]["content"] == "Session folder: C:/f/session-state/z\n\nGo."


def test_native_route_applies_it_and_records_it():
    adapter = NativeResponsesTransport(base_url="http://127.0.0.1:1/v1", model="fixture", allow_network=True,
                                       reasoning_effort="low")
    native = request()
    before = deepcopy(native)
    wire = json.loads(adapter.encode(adapter.bind(native)))
    assert native == before
    assert wire["input"] == stable_session_prefix(before)["input"]
    assert adapter.controls["stable_session_prefix"] is True
    assert "input" not in adapter.controls["changed_common_fields"]


def test_native_route_gives_the_same_history_for_any_block_split():
    adapter = NativeResponsesTransport(base_url="http://127.0.0.1:1/v1", model="fixture", allow_network=True,
                                       reasoning_effort="low")
    whole, split = request(blocks=True), request(blocks=True)
    system = whole["input"][0]["content"][0]["text"]
    cut = system.index("session-state") + 5
    split["input"][0]["content"] = [{"type": "input_text", "text": system[:cut]},
                                    {"type": "input_text", "text": system[cut:]}]
    assert adapter.bind(whole)["messages"] == adapter.bind(split)["messages"]
