"""Real subprocess CLI pipeline; synthetic fixtures are not real model quality."""
import json
from pathlib import Path
import subprocess
import sys

from brainspace import tokens
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "token_efficiency.py"


def cli(db, *args, ok=True):
    result = subprocess.run([sys.executable, str(SCRIPT), "--db", str(db), *args],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == (0 if ok else 2), result.stderr
    return json.loads(result.stdout)


def test_synthetic_cli_restart_confirm_promote_rollback(tmp_path):
    if not tokens.backend_info()["exact_reference"]:
        pytest.skip("verified local reference tokenizer unavailable; never download in tests")
    db = tmp_path / "cli.sqlite"
    initialized = cli(db, "initialize", "--synthetic")
    proposed = cli(db, "propose")
    candidate = proposed["candidates"][0]["policy_id"]
    confirmation = cli(db, "confirm", candidate, "--samples", "256", "--task-prefix", "cli-fresh")
    assert confirmation["certificate"]["decision"] == "certified"
    promoted = cli(db, "promote", str(confirmation["trial_id"]))
    assert promoted["champion"]["policy_id"] == candidate
    status = cli(db, "status")
    assert status == promoted and status["learning"]["complete_calls"] == 512
    assert status["synthetic_only"] is True
    rolled = cli(db, "rollback", "--expected-version", str(status["champion"]["version"]))
    assert rolled["champion"]["policy_id"] == initialized["champion"]["policy_id"]
    assert cli(db, "promote", '{"decision":"certified"}', ok=False)["ok"] is False


def test_cli_does_not_initialize_or_execute_shell_implicitly(tmp_path):
    db = tmp_path / "missing.sqlite"
    result = cli(db, "status", ok=False)
    assert result["reason"] == "not_initialized"
    assert not db.exists()
    result = cli(db, "initialize", ok=False)
    assert result["reason"] == "synthetic_opt_in_required"
    assert not db.exists()
