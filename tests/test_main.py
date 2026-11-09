from unittest.mock import Mock
import os
from pathlib import Path
import subprocess
import sys

import pytest

import main
from agent.settings import MISSING_API_KEY_MESSAGE
from config.settings import INPUT_NOT_FOUND_MESSAGE, INPUT_READ_ERROR_MESSAGE


def test_missing_api_key_returns_exit_code_without_release_or_traceback(monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(main, "load_dotenv", lambda path: None)
    session = Mock()
    client = Mock()
    monkeypatch.setattr(main, "RouteSession", session)
    monkeypatch.setattr(main, "OpenAI", client)

    assert main.main([]) == 1

    captured = capsys.readouterr()
    assert captured.out.strip() == MISSING_API_KEY_MESSAGE
    assert captured.err == ""
    session.assert_called_once()
    session.return_value.release.assert_not_called()
    client.assert_not_called()


@pytest.mark.parametrize("exists", [False, True])
def test_invalid_input_exits_with_readable_message(tmp_path, exists):
    input_file = tmp_path / "broken.json"
    if exists:
        input_file.write_text("{broken", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(Path(main.__file__).resolve()), str(input_file)],
        cwd=tmp_path, env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    expected = INPUT_READ_ERROR_MESSAGE if exists else INPUT_NOT_FOUND_MESSAGE
    assert result.returncode == 1
    assert result.stdout.startswith(expected.split("{path}")[0])
    assert str(input_file) in result.stdout
    assert result.stderr == "" and "Traceback" not in result.stdout
    assert not (tmp_path / "output").exists()
