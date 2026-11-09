from unittest.mock import Mock

import main
from agent.settings import MISSING_API_KEY_MESSAGE


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
    session.assert_not_called()
    client.assert_not_called()
