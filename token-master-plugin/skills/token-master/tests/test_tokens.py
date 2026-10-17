"""Reference counts must never silently become estimates."""
import json

import pytest

from brainspace import tokens


def test_special_token_literals_are_ordinary_text():
    tiktoken = pytest.importorskip("tiktoken")
    text = "literal <|endoftext|> and <|fim_prefix|>, not control tokens"
    expected = len(tiktoken.get_encoding("cl100k_base").encode_ordinary(text))
    assert tokens.count_tokens(text) == expected
    assert tokens.measure(text).exact_reference


def test_missing_tokenizer_is_not_an_exact_count(monkeypatch):
    monkeypatch.setattr(tokens, "_TRIED", True)
    monkeypatch.setattr(tokens, "_ENCODER", None)
    assert tokens.estimate("hello") == 2
    assert not tokens.measure("hello").exact_reference
    assert not tokens.guard_replacement("hello" * 50, "hello")
    with pytest.raises(tokens.ReferenceTokenizerUnavailable):
        tokens.count_tokens("hello")


def test_reference_identity_pins_vocabulary_and_protocol():
    info = tokens.backend_info()
    assert info["exact_reference"]
    assert len(info["vocabulary_id"]) == 64
    assert info["tokenizer_version"]
    assert "ordinary" in info["protocol_id"]
    assert tokens.measurement_identity("test-boundary").boundary == "test-boundary"


def test_final_envelope_is_counted_not_only_inner_text():
    before = {"content": "hello " * 100, "metadata": "unchanged"}
    after = {"content": "short", "metadata": "diagnostic overhead " * 200}
    assert tokens.count_tokens(after["content"]) < tokens.count_tokens(before["content"])
    assert not tokens.guard_replacement(before, after)


def test_wire_byte_cap_counts_serialized_unicode_envelope():
    before = {"content": "漢字" * 200}
    after = {"content": "漢字" * 50}
    raw = json.dumps(after, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert tokens.guard_replacement(before, after, max_bytes=len(raw.encode("utf-8")))
    assert not tokens.guard_replacement(before, after, max_bytes=len(raw))


def test_empty_output_and_empty_input_counts():
    assert tokens.count_tokens("") == 0
    assert not tokens.guard_replacement("", "notice")
    assert tokens.guard_replacement("hello", "")


def test_invalid_unicode_cannot_enter_exact_reference_contract():
    with pytest.raises((UnicodeError, ValueError)):
        tokens.count_tokens("\ud800")


def test_measurement_identity_is_stable_and_not_native():
    first = tokens.measurement_identity("serialized-test-boundary")
    second = tokens.measurement_identity("serialized-test-boundary")
    assert first == second
    assert first.tokenizer_id == "cl100k_base"
    assert first.vocabulary_id == tokens.VOCABULARY_SHA256
    assert first.extraction_protocol_id == "canonical-json-or-text/ordinary"
