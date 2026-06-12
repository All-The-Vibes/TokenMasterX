"""Tests for headroom/compressors/prose_compressor.py

Covers:
  (a) Near-losslessness of the default path: the set of word tokens is identical
      before and after compression (no words dropped).
  (b) Never-raises: garbage / edge-case inputs do not raise.
  (c) Determinism: calling twice yields byte-identical output.
  (d) Measured reduction on a realistic messy-prose sample (honest ~10-25%).
  (e) Stash integration: a placeholder is embedded and the original is recoverable
      via the fake stash.
  (f) Lossless when stash is None (no words removed, no placeholder injected).
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

import pytest

from headroom.compressors.prose_compressor import compress_prose
from headroom import tokens as tok_mod

# ---------------------------------------------------------------------------
# Fake in-memory stash (dict-backed, stable SHA1-12 placeholder)
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\[\[HR:[0-9a-f]{6,64}(?:\|[^\]]*)?\]\]")


def make_fake_stash():
    """Return (stash_fn, store_dict).  stash returns [[HR:<sha1-12>|<meta>]]."""
    store: dict[str, str] = {}

    def _stash(content: str, *, ctype: str = "", source: str = "", summary: str = "") -> Optional[str]:
        if not content:
            return None
        short = hashlib.sha1(content.encode("utf-8", errors="replace")).hexdigest()[:12]
        store[short] = content
        meta_parts = [p for p in (ctype, source) if p]
        meta = "; ".join(meta_parts)
        return f"[[HR:{short}|{meta}]]" if meta else f"[[HR:{short}]]"

    return _stash, store


# ---------------------------------------------------------------------------
# Realistic messy-prose sample
# ---------------------------------------------------------------------------

MESSY_PROSE = """\
Introduction to the System

This module  handles   the  core authentication workflow.    It is responsible
for verifying user credentials,  issuing session tokens,  and revoking them on
logout or  expiry.



The design prioritises security over convenience.   Every token is stored as a
bcrypt hash.    Replay  attacks are  mitigated  by embedding a nonce.


Implementation Notes

The  session store  uses  Redis as  a  primary  cache  with  a  fallback  to
Postgres   for   durability.   TTLs   are   set   per   user   tier:    free
accounts  expire  in  24  hours;   pro  accounts  in  30  days.



Error Handling

All  errors  are  surfaced  as  structured  JSON  with  a  machine-readable
``error_code``  field.    This  lets  clients  handle  errors  programmatically
without   scraping   human-readable  messages.    The  canonical  error  list   is
maintained  in  ``docs/errors.md``.    Contributions  welcome!



Deployment Considerations

The service  is  deployed  as  a  Kubernetes  Deployment  with  3  replicas.
Horizontal pod  autoscaling  is  enabled;  the  HPA  target  is  70%  CPU.
Liveness and  readiness  probes  hit  ``GET /healthz``  every  10  seconds.    A
PodDisruptionBudget  ensures  at  least  1  replica  is  always  available.   The
container  image  is  published  to  ``ghcr.io/org/auth-service:latest``  by  the
GitHub Actions  release  workflow.


Conclusion

Security  is   never   done.    We  continuously  monitor  CVE  feeds   and  run
automated  SAST  on  every  PR.    The  threat  model  is  reviewed  quarterly.
"""


def _word_tokens(text: str) -> set[str]:
    """Extract the set of whitespace-separated tokens for losslessness checks."""
    return set(re.findall(r"\S+", text))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDefaultPath:
    """Default path: use_ml=False, stdlib only."""

    def test_near_lossless_no_stash(self):
        """No words are removed when stash is None (lossless mode)."""
        result = compress_prose(MESSY_PROSE, stash=None)
        before_words = _word_tokens(MESSY_PROSE)
        after_words = _word_tokens(result)
        # The compressed output must contain every word that was in the input.
        # (It may contain *extra* tokens like the stash placeholder — but those
        # are additive, not subtractive.)
        missing = before_words - after_words
        assert not missing, f"Words removed from output: {missing}"

    def test_near_lossless_with_stash_small(self):
        """For small content (<=2000 chars) with stash, no placeholder is added."""
        stash_fn, store = make_fake_stash()
        small = MESSY_PROSE[:400]
        result = compress_prose(small, stash=stash_fn)
        before_words = _word_tokens(small)
        after_words = _word_tokens(result)
        missing = before_words - after_words
        assert not missing, f"Words removed: {missing}"
        # No placeholder should have been injected for small content.
        assert "[[HR:" not in result

    def test_stash_placeholder_injected_for_large_content(self):
        """For large content (>2000 chars), a placeholder is appended."""
        stash_fn, store = make_fake_stash()
        # Pad prose to ensure it exceeds the 2000-char threshold.
        large = MESSY_PROSE * 3
        assert len(large) > 2_000
        result = compress_prose(large, stash=stash_fn)
        assert "[[HR:" in result, "Expected a placeholder in the output for large content"
        # The placeholder must be a validly shaped HR token.
        placeholders = _PLACEHOLDER_RE.findall(result)
        assert placeholders, "No well-formed [[HR:...]] placeholder found"

    def test_stash_roundtrip_recovers_original(self):
        """Extracting the placeholder hash and looking up the store returns original."""
        stash_fn, store = make_fake_stash()
        large = MESSY_PROSE * 3
        result = compress_prose(large, stash=stash_fn)
        m = _PLACEHOLDER_RE.search(result)
        assert m, "No placeholder found"
        # Extract the short hash from the placeholder [[HR:<hash>|...]]
        inner = m.group(0)  # e.g. "[[HR:abc123def456|prose]]"
        short = re.search(r"\[\[HR:([0-9a-f]+)", inner).group(1)
        assert short in store, f"Hash {short!r} not found in fake stash store"
        recovered = store[short]
        assert recovered == large, "Recovered content does not match original"

    def test_determinism(self):
        """Two calls with the same input and stash give byte-identical output."""
        stash_fn, _ = make_fake_stash()
        out1 = compress_prose(MESSY_PROSE, stash=stash_fn)
        # Fresh stash that produces the same hashes (SHA1 is deterministic).
        stash_fn2, _ = make_fake_stash()
        out2 = compress_prose(MESSY_PROSE, stash=stash_fn2)
        assert out1 == out2, "Output is not deterministic"

    def test_determinism_no_stash(self):
        """Determinism also holds without a stash."""
        out1 = compress_prose(MESSY_PROSE, stash=None)
        out2 = compress_prose(MESSY_PROSE, stash=None)
        assert out1 == out2


class TestNeverRaises:
    """Garbage and edge-case inputs must not raise."""

    @pytest.mark.parametrize("bad_input", [
        pytest.param("", id="empty"),
        pytest.param(None, id="none"),  # type: ignore[arg-type]  -- intentionally wrong type
        pytest.param("\x00\xff\n\t", id="binary"),
        pytest.param("   ", id="spaces"),
        pytest.param("\n\n\n\n\n", id="blank_lines"),
        pytest.param("a" * 50_000, id="very_large"),   # very large
        pytest.param("word " * 1_000, id="many_words"),
    ])
    def test_no_raise_on_bad_input(self, bad_input):
        try:
            result = compress_prose(bad_input, stash=None)
        except Exception as exc:
            pytest.fail(f"compress_prose raised on input {bad_input!r:.40}: {exc}")
        # Result must always be a str.
        assert isinstance(result, str)

    def test_no_raise_with_broken_stash(self):
        """A stash that always raises must not propagate the error."""
        def bad_stash(content, **_):
            raise RuntimeError("stash exploded")

        large = MESSY_PROSE * 3
        try:
            result = compress_prose(large, stash=bad_stash)
        except Exception as exc:
            pytest.fail(f"compress_prose raised despite bad stash: {exc}")
        assert isinstance(result, str)

    def test_no_raise_with_stash_returning_none(self):
        """A stash that returns None (failure) must not cause placeholder injection."""
        def none_stash(content, **_):
            return None

        large = MESSY_PROSE * 3
        result = compress_prose(large, stash=none_stash)
        assert isinstance(result, str)
        assert "[[HR:" not in result, "Placeholder injected even though stash returned None"

    def test_no_raise_use_ml_false(self):
        """use_ml=False must never raise even on weird input."""
        result = compress_prose("Hello   world.\n\n\n\n\nGoodbye.", stash=None, use_ml=False)
        assert isinstance(result, str)


class TestWhitespaceNormalisation:
    """Detailed checks that the default-path transforms work correctly."""

    def test_trailing_whitespace_stripped(self):
        text = "hello   \nworld  \n"
        result = compress_prose(text, stash=None)
        for line in result.splitlines():
            assert line == line.rstrip(), f"Trailing whitespace in line: {line!r}"

    def test_blank_line_runs_collapsed(self):
        text = "para1\n\n\n\n\npara2\n\n\n\npara3"
        result = compress_prose(text, stash=None)
        # Should not contain 3+ consecutive newlines.
        assert "\n\n\n" not in result

    def test_interior_spaces_collapsed(self):
        text = "foo  bar   baz\nindented    content"
        result = compress_prose(text, stash=None)
        # Interior double-spaces should be gone.
        lines = result.splitlines()
        # "foo  bar" -> "foo bar"
        assert "foo bar baz" in lines[0]

    def test_leading_indentation_preserved(self):
        """Leading spaces (indentation) must NOT be collapsed."""
        text = "    def foo():\n        pass\n"
        result = compress_prose(text, stash=None)
        assert result.startswith("    def foo():")


class TestMeasuredReduction:
    """Report an honest measured reduction figure (expected ~10-25%)."""

    def test_measured_reduction(self):
        result = compress_prose(MESSY_PROSE, stash=None)
        report = tok_mod.reduction(MESSY_PROSE, result)
        print(
            f"\n[prose reduction] {report['tokens_before']} -> {report['tokens_after']} tokens "
            f"({report['pct_reduction']}% reduction, {report['ratio']}x, backend={report['backend']})"
        )
        # The default path is conservative; we expect at least 1% (whitespace savings).
        assert report["pct_reduction"] >= 1.0, (
            f"Expected at least 1% reduction, got {report['pct_reduction']}%"
        )
        # And it should not be wildly lossy (no more than 50% for the default path).
        assert report["pct_reduction"] <= 50.0, (
            f"Too aggressive for a whitespace-only path: {report['pct_reduction']}%"
        )
        # Store the measured string for StructuredOutput reporting.
        TestMeasuredReduction.last_report = (
            f"prose sample: {report['tokens_before']}->{report['tokens_after']} tok, "
            f"{report['pct_reduction']}%"
        )
