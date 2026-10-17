"""Prose is exact: word-set equality does not preserve literal text."""

from __future__ import annotations

import hashlib
from typing import Optional

import pytest

from brainspace.compressors.prose_compressor import compress_prose
from brainspace import tokens as tok_mod

# ---------------------------------------------------------------------------
# Fake in-memory stash (dict-backed, stable SHA1-12 placeholder)
# ---------------------------------------------------------------------------

def make_fake_stash():
    """Return (stash_fn, store_dict).  stash returns [[BR:<sha1-12>|<meta>]]."""
    store: dict[str, str] = {}

    def _stash(content: str, *, ctype: str = "", source: str = "", summary: str = "") -> Optional[str]:
        if not content:
            return None
        short = hashlib.sha1(content.encode("utf-8", errors="replace")).hexdigest()[:12]
        store[short] = content
        meta_parts = [p for p in (ctype, source) if p]
        meta = "; ".join(meta_parts)
        return f"[[BR:{short}|{meta}]]" if meta else f"[[BR:{short}]]"

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


class TestExactProse:
    @pytest.mark.parametrize("text", [MESSY_PROSE, MESSY_PROSE * 3, "", None,
                                      "a" * 50_000, "   ", "\n\n\n\n\n",
                                      "\x00\xff\n\t", "word " * 1000],
                             ids=["messy", "large", "empty", "none", "long", "spaces", "newlines", "binary", "words"])
    @pytest.mark.parametrize("intent", ["conservative", "overview", "navigation", "exact"])
    def test_byte_exact_with_or_without_stash(self, text, intent):
        stash, store = make_fake_stash()
        assert compress_prose(text, stash=stash, intent=intent) == text
        assert compress_prose(text, intent=intent) == text
        assert not store

    @pytest.mark.parametrize("text", [
        "hello   \nworld  \n", "para1\n\n\n\n\npara2",
        "foo  bar   baz\nindented    content", "    def foo():\n        pass\n",
        'The exact literal is "a  b".', "inline `a  b` and hard break  \nnext",
        "~~~text\n  code  \n~~~", "before\r\n\r\nafter\r\n",
    ])
    def test_whitespace_is_not_assumed_insignificant(self, text):
        assert compress_prose(text) == text

    def test_broken_storage_cannot_change_text(self):
        def bad_stash(*_, **__):
            raise OSError("full")
        assert compress_prose(MESSY_PROSE * 3, stash=bad_stash) == MESSY_PROSE * 3

    def test_legacy_options_remain_accepted_without_model_calls(self):
        assert compress_prose(MESSY_PROSE, use_ml=True, rate=0.01,
                              budget=1, future_option=True) == MESSY_PROSE

    def test_measured_savings_are_not_claimed_for_passthrough(self):
        result = compress_prose(MESSY_PROSE)
        report = tok_mod.reduction(MESSY_PROSE, result)
        assert report["pct_reduction"] == 0.0
