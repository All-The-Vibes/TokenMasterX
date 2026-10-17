"""Installed CLIs must work outside the source checkout, not only via PYTHONPATH."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from brainspace.tokens import _vocabulary_path

SKILL = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("host", ["claude", "codex", "copilot"])
def test_installed_efficiency_and_mode_entrypoints(tmp_path, host):
    home = tmp_path / "isolated home 空白"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP")
           if key in os.environ}
    env.update(
        HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(home),
        CLAUDE_CONFIG_DIR=str(home), CLAUDE_HOME=str(home), COPILOT_HOME=str(home),
        PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(SKILL / "brainspace_setup.py"), "--host", host,
         "--python", sys.executable, "--tokenizer-file", str(_vocabulary_path())],
        cwd=workspace, env=env, capture_output=True, encoding="utf-8", timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    installed = home / "token-master"
    assert (installed / "brainspace_tools.py").is_file()
    assert (installed / "token_efficiency.py").is_file()
    assert (installed / "evals" / "synthetic_efficiency.py").is_file()
    env["BRAINSPACE_TOKENIZER_FILE"] = str(installed / "tokenizer/cl100k_base.tiktoken")
    for argv in (
        [str(installed / "brainspace_tools.py"), "--workspace", str(workspace),
         "--session", "unrelated-session", "mode-status"],
        [str(installed / "token_efficiency.py"), "--db", str(workspace / "demo.sqlite"),
         "initialize", "--synthetic"],
    ):
        ran = subprocess.run([sys.executable, *argv], cwd=workspace, env=env,
                             capture_output=True, encoding="utf-8", timeout=30)
        assert ran.returncode == 0, ran.stdout + ran.stderr
        assert isinstance(json.loads(ran.stdout), dict)
