"""Explicit mechanism studies must not masquerade as fresh holdouts."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
import run_retention as trial  # noqa: E402


def arguments(tmp_path):
    return ["--output", str(tmp_path / "out"), "--reference-study", str(tmp_path / "reference"),
            "--candidate", str(tmp_path / "candidate.json"), "--allow-network", "--frozen"]


def test_mechanism_case_and_order_are_explicit_controls(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(trial, "execute", lambda args: seen.append(args) or 0)
    assert trial.main([*arguments(tmp_path), "--mechanism-case", "retention_installed_demo_trace",
                       "--order-seed", "2"]) == 0
    assert seen[0].mechanism_case == "retention_installed_demo_trace"
    assert seen[0].replication is False and seen[0].order_seed == 2


def test_old_holdout_defaults_are_preserved(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(trial, "execute", lambda args: seen.append(args) or 0)
    assert trial.main(arguments(tmp_path)) == 0
    assert seen[0].mechanism_case is None
    assert seen[0].replication is False and seen[0].order_seed == 20261009


def test_exposed_case_cannot_be_labeled_fresh_replication(tmp_path, monkeypatch):
    monkeypatch.setattr(trial, "execute", lambda _: pytest.fail("invalid controls must not execute"))
    with pytest.raises(SystemExit) as error:
        trial.main([*arguments(tmp_path), "--replication", "--mechanism-case", "old-case"])
    assert error.value.code == 2


@pytest.mark.parametrize("seed", ["-1", str(2**32)])
def test_invalid_order_seed_rejects_before_execution(tmp_path, monkeypatch, seed):
    monkeypatch.setattr(trial, "execute", lambda _: pytest.fail("invalid seed must not execute"))
    with pytest.raises(SystemExit) as error:
        trial.main([*arguments(tmp_path), "--order-seed", seed])
    assert error.value.code == 2
