from unittest.mock import Mock
from io import StringIO
from types import SimpleNamespace
import os
from pathlib import Path
import subprocess
import sys

import pytest
from dotenv import load_dotenv
from openai.types.chat import ChatCompletionMessage

import main
from agent.settings import MISSING_API_KEY_MESSAGE
from agent import settings
from config.settings import INPUT_NOT_FOUND_MESSAGE, INPUT_READ_ERROR_MESSAGE


def test_missing_api_key_returns_exit_code_without_release_or_traceback(monkeypatch, capsys):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
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


@pytest.mark.parametrize("model, base_url", [
    (settings.MODEL, settings.BASE_URL),
    ("other-model", "https://example.test/v1"),
])
def test_environment_configures_client_request_and_log(input_file, tmp_path, monkeypatch, capsys, model, base_url):
    monkeypatch.setenv("LLM_API_KEY", "environment-key")
    monkeypatch.setenv("LLM_MODEL", model)
    monkeypatch.setenv("LLM_BASE_URL", base_url)
    file_values = "LLM_API_KEY=file-key\nLLM_MODEL=file-model\nLLM_BASE_URL=https://file.test/v1"
    monkeypatch.setattr(main, "load_dotenv", lambda path: load_dotenv(stream=StringIO(file_values)))
    folder = tmp_path / "output"
    monkeypatch.setattr(main, "OUTPUT_DIR", folder)
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=ChatCompletionMessage(role="assistant", content="Ответ"))],
        usage=SimpleNamespace(prompt_tokens=20, completion_tokens=5),
    )
    factory = Mock(return_value=client)
    monkeypatch.setattr(main, "OpenAI", factory)
    monkeypatch.setattr("builtins.input", Mock(side_effect=["Ответь", "выход"]))
    main.main([str(input_file)])
    factory.assert_called_once_with(api_key="environment-key", base_url=base_url)
    request = client.chat.completions.create.call_args.kwargs
    assert request["model"] == model
    if base_url == settings.BASE_URL:
        assert request["extra_body"] == settings.MODEL_EXTRA_BODY
    else:
        assert "extra_body" not in request
    header = settings.MODEL_INFO_TEMPLATE.format(model=model, base_url=base_url)
    console = capsys.readouterr().out
    journal = (folder / "tool_log.md").read_text(encoding="utf-8")
    assert console.splitlines().count(header) == journal.splitlines().count(header) == 1
    assert "вход 20 (кэш 0) / выход 5" in console and "Итог сессии:" in journal
    if model != settings.MODEL:
        assert settings.UNPRICED_COST_MESSAGE in console and settings.UNPRICED_COST_MESSAGE in journal
        assert "$" not in journal and settings.PRICE_NOTE not in journal
