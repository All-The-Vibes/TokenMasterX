"""Tests for the isolated sandbox >=30% whole-task savings benchmark."""
from __future__ import annotations

from pathlib import Path
import sys

EVALS = Path(__file__).resolve().parents[3] / "evals"
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

from run_isolated_sandbox_savings import build_isolated_sandbox_env, run_study  # noqa: E402


REPO = Path(__file__).resolve().parents[4]
VOCAB = REPO / "evidence/controlled-scorecard-20261008/batch-001/cl100k_base.tiktoken"


def test_build_isolated_sandbox_env_strips_global_headroom_and_ponytail(tmp_path: Path):
    env = build_isolated_sandbox_env(tmp_path / "sb", VOCAB)
    for key in env:
        assert not key.startswith(("HEADROOM_", "ANTHROPIC_", "OPENAI_", "OPENCODE_", "PONYTAIL_"))
    assert Path(env["HOME"]).is_relative_to(tmp_path / "sb")
    assert Path(env["USERPROFILE"]).is_relative_to(tmp_path / "sb")
    assert Path(env["CLAUDE_CONFIG_DIR"]).is_relative_to(tmp_path / "sb")
    assert Path(env["COPILOT_HOME"]).is_relative_to(tmp_path / "sb")
    assert Path(env["CODEX_HOME"]).is_relative_to(tmp_path / "sb")


def test_isolated_sandbox_study_achieves_30_percent_plus_savings(tmp_path: Path):
    out = tmp_path / "study-run"
    summary = run_study(out, VOCAB)
    assert summary["sandbox_isolation"]["isolated"] is True
    assert summary["sandbox_isolation"]["leaked_environment_variables"] == []
    assert summary["sandbox_isolation"]["global_headroom_present_in_sandbox"] is False
    assert summary["sandbox_isolation"]["global_ponytail_present_in_sandbox"] is False
    assert summary["all_tasks_correct"] is True
    assert summary["by_arm"]["baseline"]["correct"] == 6
    assert summary["by_arm"]["tokenmaster_v5"]["correct"] == 6
    assert summary["by_arm"]["baseline"]["model_calls"] == 30
    assert summary["by_arm"]["tokenmaster_v5"]["model_calls"] == 30
    assert summary["savings"]["meets_30_percent_target"] is True
    assert summary["savings"]["gateway_reported_savings_pct"] >= 30.0
    assert summary["savings"]["reference_total_savings_pct"] >= 30.0
