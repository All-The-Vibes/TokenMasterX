import pytest

from brainspace.jev import JevClient


QUESTION = {"q": {"type": "choice", "instructions": "Choose.",
                  "criteria": {"keep": None, "skip": None}}}


def test_oversized_request_never_reads_credentials_or_sends(monkeypatch):
    def forbidden(*args):
        raise AssertionError("must reject before credential access")
    monkeypatch.setattr("brainspace.jev.os.getenv", forbidden)
    result = JevClient(enabled=True, allow_network=True, max_request_bytes=256).decide(
        "large synthetic input" * 100, QUESTION, data_classification="synthetic")
    assert not result.ok
    assert result.reason == "request_too_large"
    assert result.diagnostics.attempts == 0
    assert result.request_text is None


@pytest.mark.parametrize("value", [0, -1, True, 4_194_305, "1024"])
def test_invalid_request_limits_reject(value):
    with pytest.raises(ValueError):
        JevClient(max_request_bytes=value)
