from datetime import datetime, timezone
from types import SimpleNamespace

from agent import usage as usage_module
from unittest.mock import Mock

import pytest
from openai.types.chat import ChatCompletionMessage

from agent import runtime, settings
from agent.runtime import RouteAgent
from agent.usage import TokenUsage
from core.session import RouteSession


def test_token_usage_add_and_cost(monkeypatch):
    monkeypatch.setattr(settings, "PRICE_INPUT_CACHE_HIT_PER_M", 0.1)
    monkeypatch.setattr(settings, "PRICE_INPUT_CACHE_MISS_PER_M", 0.2)
    monkeypatch.setattr(settings, "PRICE_OUTPUT_PER_M", 0.3)
    clock = Mock()
    clock.now.return_value = datetime(2026, 11, 9, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(usage_module, "datetime", clock)
    usage = TokenUsage()
    usage.add(SimpleNamespace(prompt_cache_hit_tokens=200_000, prompt_cache_miss_tokens=300_000,
                              completion_tokens=500_000))
    usage.add(SimpleNamespace(prompt_tokens=100_000, completion_tokens=100_000))
    usage.add(None)
    assert usage.prompt_cache_hit_tokens == 200_000
    assert usage.prompt_cache_miss_tokens == 400_000
    assert usage.completion_tokens == 600_000
    assert usage.cost_usd == pytest.approx(0.28)


def test_question_and_session_usage_are_logged(input_file, tmp_path, config, monkeypatch, capsys):
    session = RouteSession(input_file, tmp_path / "output", config)
    client = Mock()
    replies = []
    for tokens in [SimpleNamespace(prompt_cache_hit_tokens=20, prompt_cache_miss_tokens=10, completion_tokens=4),
                   SimpleNamespace(prompt_cache_hit_tokens=40, prompt_cache_miss_tokens=30, completion_tokens=6),
                   SimpleNamespace(prompt_tokens=20, completion_tokens=5)]:
        message = ChatCompletionMessage(role="assistant", content="Ответ")
        replies.append(SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=tokens))
    replies[0].choices[0].message = ChatCompletionMessage(role="assistant", content=None, tool_calls=[
        {"id": "call_1", "type": "function", "function": {"name": "calculate_route_length", "arguments": "{}"}},
    ])
    client.chat.completions.create.side_effect = replies
    monkeypatch.setattr(runtime, "perf_counter", Mock(side_effect=[10, 12, 20, 23]))
    agent = RouteAgent(client, {"calculate_route_length": lambda: {}}, "Помощник", tool_log=session.tool_log)
    session.usage_log = agent.usage_log
    assert agent.ask("Первый вопрос") == "Ответ"
    first = capsys.readouterr().out
    assert "вопрос 1: время 2,00 с, токены вход 100 (кэш 60) / выход 10, стоимость $" in first
    assert agent.ask("Второй вопрос") == "Ответ"
    assert "вопрос 2: время 3,00 с, токены вход 20 (кэш 0) / выход 5, стоимость $" in capsys.readouterr().out
    assert (agent.question_usage.prompt_cache_hit_tokens, agent.question_usage.prompt_cache_miss_tokens,
            agent.question_usage.completion_tokens) == (0, 20, 5)
    assert (agent.session_usage.prompt_cache_hit_tokens, agent.session_usage.prompt_cache_miss_tokens,
            agent.session_usage.completion_tokens) == (60, 60, 15)
    assert agent.session_elapsed == 5
    assert len(agent.usage_log) == 2 and len(session.tool_log) == 1
    session.save_tool_log()
    journal = (session.output_dir / "tool_log.md").read_text(encoding="utf-8")
    assert next(line for line in first.splitlines() if "время" in line) in journal
    assert "Итог сессии: время 5,00 с, токены вход 120 (кэш 60) / выход 15" in journal
    assert settings.PRICE_NOTE in journal
    assert "," in journal.split("стоимость $")[1].splitlines()[0]
    assert len(journal.split("стоимость $")[1].splitlines()[0].split(",")[1]) == 6


@pytest.mark.parametrize("weekday, hour, cost", [
    (9, 0, 0.01503), (9, 1, 0.03006), (9, 3, 0.03006), (9, 4, 0.01503),
    (9, 6, 0.03006), (9, 9, 0.03006), (9, 10, 0.01503), (14, 2, 0.01503), (15, 7, 0.01503),
])
def test_usage_prices_each_response_at_utc_time(monkeypatch, weekday, hour, cost):
    clock = Mock()
    clock.now.return_value = datetime(2026, 11, weekday, hour, tzinfo=timezone.utc)
    monkeypatch.setattr(usage_module, "datetime", clock)
    usage = TokenUsage()
    tokens = SimpleNamespace(prompt_cache_hit_tokens=10_000, prompt_cache_miss_tokens=20_000, completion_tokens=20_000)
    usage.add(tokens)
    assert usage.cost_usd == pytest.approx(cost)
    clock.now.assert_called_once_with(timezone.utc)
    clock.now.return_value = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    usage.add(tokens)
    assert usage.cost_usd == pytest.approx(cost + 0.01503)
    monkeypatch.setattr(settings, "PRICE_OUTPUT_PER_M", 100)
    assert usage.cost_usd == pytest.approx(cost + 0.01503)
