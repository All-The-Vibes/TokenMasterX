import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from quality.measurement import context_texts  # noqa: E402


def test_projection_preserves_context_but_not_vendor_usage_metadata():
    request = {"model": "fixture", "input": [{"role": "user", "content": "a \n b"}],
               "tools": [], "store": False, "stream": False}
    response = {"id": "random-server-id", "usage": {"input_tokens": 999999},
                "output": [{"type": "message", "role": "assistant", "id": "another-id",
                            "content": [{"type": "output_text", "text": "answer"}]}]}
    before, after = context_texts(request, response)
    assert json.loads(before)["input"][0]["content"] == "a \n b"
    assert "answer" in after
    assert "999999" not in after and "random-server-id" not in after
    response["usage"]["input_tokens"] = 0
    assert context_texts(request, response) == (before, after)


def test_call_and_result_pair_ids_and_arguments_are_retained():
    request = {"input": [{"type": "function_call", "call_id": "pair", "name": "read",
                         "arguments": '{"path":"x"}'},
                        {"type": "function_call_output", "call_id": "pair", "output": "literal"}]}
    response = {"output": [{"type": "function_call", "id": "server-id", "call_id": "next",
                           "name": "answer", "arguments": '{"content":"yes"}'}]}
    before, after = map(json.loads, context_texts(request, response))
    assert before["input"][0]["call_id"] == before["input"][1]["call_id"] == "pair"
    assert after[0]["call_id"] == "next" and "id" not in after[0]


def test_opaque_state_is_not_a_materialized_context():
    with pytest.raises(ValueError):
        context_texts({"input": [{"type": "item_reference", "id": "hidden"}]},
                      {"output": []})
    with pytest.raises(ValueError):
        context_texts({"input": []}, {"output": [{"type": "reasoning",
                                                "encrypted_content": "opaque"}]})
