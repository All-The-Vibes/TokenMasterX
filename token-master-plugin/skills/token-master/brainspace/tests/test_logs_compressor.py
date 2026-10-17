"""Tests for brainspace.compressors.logs_compressor.

Run from the skill dir so 'import brainspace' resolves:

    cd "C:/Users/shyamsridhar/code/TokenMaster/token-master-plugin/skills/token-master"
    uv run --with mcp --with pytest python -m pytest brainspace/tests/test_logs_compressor.py -q

The test suite verifies:
  (a) lossless recovery -- the stash stores the exact original; the placeholder
      is embedded so a real CCR.retrieve call would return it.
  (b) never-raises on garbage / edge-case input
  (c) determinism -- calling twice gives identical bytes
  (d) a real measured reduction on a ~500-line build/test log
"""

from __future__ import annotations

import hashlib

import pytest


# ---------------------------------------------------------------------------
# Fake in-memory stash (no SQLite dependency)
# ---------------------------------------------------------------------------

def make_fake_stash():
    """Return a (stash_fn, store_dict) pair.

    stash_fn(content, *, ctype='', source='', summary='') -> placeholder str
    store_dict maps placeholder -> original content for recovery checks.
    """
    store: dict[str, str] = {}

    def _stash(content: str, *, ctype: str = "", source: str = "", summary: str = "",
               kind: str = "fragment") -> str | None:
        if not content:
            return None
        raw = content.encode("utf-8", errors="replace")
        short = hashlib.sha256(raw).hexdigest()[:12]
        meta_parts = [p for p in (ctype, source or summary) if p]
        n_lines = content.count("\n") + 1
        meta_parts.append(f"{n_lines}L")
        meta = "; ".join(meta_parts)
        placeholder = f"[[BR:{short}|{meta}]]"
        store[placeholder] = content
        return placeholder

    return _stash, store


# ---------------------------------------------------------------------------
# Realistic log sample builders
# ---------------------------------------------------------------------------

def make_build_log(n_info: int = 450, error_at: list[int] | None = None) -> str:
    """Build a synthetic ~500-line build/test log.

    The log has INFO-dominated sections with ERROR/Traceback blocks injected
    at the specified line indices (defaults to two blocks near lines 150 and 350).
    """
    if error_at is None:
        error_at = [150, 350]

    error_set = set(error_at)
    lines = []

    # Header
    lines.append("[INFO] Build started: myapp v1.2.3\n")
    lines.append("[INFO] Loading configuration from setup.cfg\n")
    lines.append("[INFO] Resolving 47 dependencies...\n")

    info_i = 0
    line_idx = len(lines)

    while info_i < n_info:
        target = line_idx + info_i
        if target in error_set:
            # Inject an error block (Traceback + ERROR lines)
            lines.append("[ERROR] Test failed: test_validate_array\n")
            lines.append("Traceback (most recent call last):\n")
            lines.append("  File \"tests/test_core.py\", line 42, in test_validate_array\n")
            lines.append("    result = validate_array(data)\n")
            lines.append("  File \"src/core.py\", line 88, in validate_array\n")
            lines.append("    raise ValueError(f\"Array length {len(arr)} exceeds limit\")\n")
            lines.append("ValueError: Array length 10001 exceeds limit\n")
            lines.append("[FATAL] Cannot continue: critical validation failure\n")
            info_i += 8  # counted as progress
        else:
            mod = info_i % 20
            if mod == 0:
                lines.append(f"[INFO] Running test module {info_i // 20 + 1} of 23\n")
            elif mod < 5:
                lines.append(f"[DEBUG] test_case_{info_i} ... ok\n")
            elif mod < 10:
                lines.append(f"[INFO] Compiling module_{info_i % 7}.py\n")
            else:
                lines.append(f"[DEBUG] Cache hit for key={hex(info_i)}\n")
            info_i += 1

    # A second error block (WARN + Exception)
    lines.append("[WARN] Deprecated API call: use new_api() instead\n")
    lines.append("[ERROR] Exception in worker thread\n")
    lines.append("Exception: connection pool exhausted after 30s\n")

    # Footer
    lines.append("[INFO] Build finished in 42.3s\n")
    lines.append("[INFO] 487 tests run, 2 failures\n")

    return "".join(lines)


def make_success_log(n=100):
    return "".join(f"[INFO] Compiling module_{i}.py\n" for i in range(n)) + "[INFO] Build succeeded\n"


def make_repeated_log() -> str:
    """A log with long runs of the same INFO line."""
    lines = []
    lines.append("[INFO] Server started\n")
    for _ in range(50):
        lines.append("[INFO] Polling queue (empty)...\n")
    lines.append("[ERROR] Queue poll timed out after 60s\n")
    for _ in range(30):
        lines.append("[DEBUG] heartbeat ok\n")
    lines.append("[INFO] Server stopped\n")
    return "".join(lines)


# ---------------------------------------------------------------------------
# Import helper
# ---------------------------------------------------------------------------

def import_compressor():
    from brainspace.compressors.logs_compressor import compress_logs
    return compress_logs


# ---------------------------------------------------------------------------
# (b) Never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    """Rule 1: the function must never raise."""

    def test_empty_string(self):
        compress_logs = import_compressor()
        result = compress_logs("")
        assert isinstance(result, str)

    def test_whitespace_only(self):
        compress_logs = import_compressor()
        result = compress_logs("   \n\t\n  ")
        assert isinstance(result, str)

    def test_none_input(self):
        compress_logs = import_compressor()
        result = compress_logs(None)  # type: ignore[arg-type]
        assert result is None  # returned unchanged per contract

    def test_binary_garbage(self):
        compress_logs = import_compressor()
        garbage = "\x00\xff\xfe\x80" * 50
        result = compress_logs(garbage)
        assert isinstance(result, str)

    def test_single_line(self):
        compress_logs = import_compressor()
        result = compress_logs("one line\n")
        assert isinstance(result, str)

    def test_few_lines_returned_unchanged(self):
        """Fewer than _MIN_LOG_LINES lines => return unchanged."""
        compress_logs = import_compressor()
        short = "line1\nline2\nline3\n"
        result = compress_logs(short)
        assert result == short

    def test_unknown_opts_ignored(self):
        compress_logs = import_compressor()
        log = make_build_log()
        result = compress_logs(log, bogus_opt="yes", another=42)
        assert isinstance(result, str)

    def test_stash_that_always_raises(self):
        compress_logs = import_compressor()

        def bad_stash(content, **kwargs):
            raise RuntimeError("stash exploded!")

        result = compress_logs(make_build_log(), stash=bad_stash)
        assert isinstance(result, str)

    def test_stash_returning_none(self):
        compress_logs = import_compressor()
        result = compress_logs(make_build_log(), stash=lambda *a, **kw: None)
        assert isinstance(result, str)

    def test_very_large_input(self):
        compress_logs = import_compressor()
        big = make_build_log(n_info=5000)
        result = compress_logs(big)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# (c) Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Rule 4: same input + same opts + same stash => byte-identical output."""

    def test_deterministic_without_stash(self):
        compress_logs = import_compressor()
        log = make_build_log()
        r1 = compress_logs(log)
        r2 = compress_logs(log)
        assert r1 == r2

    def test_deterministic_with_stash(self):
        compress_logs = import_compressor()
        log = make_build_log()
        stash1, _ = make_fake_stash()
        stash2, _ = make_fake_stash()
        r1 = compress_logs(log, stash=stash1)
        r2 = compress_logs(log, stash=stash2)
        assert r1 == r2, (
            "Two calls with separate but identical stash implementations must "
            "produce byte-identical output (stash keys are content-addressed)"
        )

    def test_deterministic_repeated_log(self):
        compress_logs = import_compressor()
        log = make_repeated_log()
        r1 = compress_logs(log)
        r2 = compress_logs(log)
        assert r1 == r2

    def test_deterministic_different_context(self):
        compress_logs = import_compressor()
        log = make_build_log()
        r1 = compress_logs(log, context=0)
        r2 = compress_logs(log, context=0)
        assert r1 == r2


# ---------------------------------------------------------------------------
# (a) Lossless recovery
# ---------------------------------------------------------------------------

class TestLosslessRecovery:
    def test_successful_overview_full_log_stashed(self):
        stash, store = make_fake_stash()
        text = make_success_log()
        out = import_compressor()(text, stash=stash, intent="overview")
        assert "overview (lossy)" in out
        assert "lines elided" in out
        ref = out.split("full log: ")[1].strip()
        assert store[ref] == text
        assert text.splitlines()[0] in out
        assert text.splitlines()[-1] in out

    def test_default_even_successful_log_is_exact(self):
        stash, store = make_fake_stash()
        text = make_success_log()
        assert import_compressor()(text, stash=stash) == text
        assert not store

    @pytest.mark.parametrize("builder", [make_build_log, make_repeated_log])
    def test_failures_keep_all_causal_context_even_in_overview(self, builder):
        stash, store = make_fake_stash()
        text = builder()
        assert import_compressor()(text, stash=stash, intent="overview", context=0) == text
        assert not store

    def test_no_lossy_output_without_stash(self):
        text = make_success_log()
        assert import_compressor()(text, intent="overview") == text

    def test_failed_stash_is_exact(self):
        text = make_success_log()
        assert import_compressor()(text, stash=lambda *a, **kw: None, intent="overview") == text

    def test_unknown_final_state_is_passthrough(self):
        text = make_success_log().replace("Build succeeded", "Build status unknown")
        stash, store = make_fake_stash()
        assert import_compressor()(text, stash=stash, intent="overview") == text
        assert not store

    @pytest.mark.parametrize("context", [-1, None, True, "two"])
    def test_invalid_context_is_passthrough(self, context):
        text = make_success_log()
        stash, _ = make_fake_stash()
        assert import_compressor()(text, stash=stash, intent="overview", context=context) == text



# ---------------------------------------------------------------------------
# (d) Measured reduction on a realistic ~500-line build log
# ---------------------------------------------------------------------------

class TestMeasuredReduction:
    def test_successful_overview_reduction(self):
        from brainspace import tokens
        text = make_success_log(450)
        stash, _ = make_fake_stash()
        out = import_compressor()(text, stash=stash, intent="overview")
        report = tokens.reduction(text, out)
        print(f"\nLog overview: {report}")
        assert report["pct_reduction"] >= 50.0

    def test_failed_build_has_no_artificial_savings(self):
        text = make_build_log(450)
        stash, _ = make_fake_stash()
        assert import_compressor()(text, stash=stash, intent="overview") == text
