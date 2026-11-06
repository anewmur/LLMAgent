import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai.types.chat import ChatCompletionMessage

from agent import runtime


def response(content=None, tool_name=None, arguments="{}", call_id="call_1"):
    calls = None
    if tool_name:
        calls = [{
            "id": call_id, "type": "function",
            "function": {"name": tool_name, "arguments": arguments},
        }]
    message = ChatCompletionMessage(
        role="assistant", content=content, tool_calls=calls
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_questions_preserve_history_and_execute_tools(monkeypatch):
    handler = Mock(return_value={"status": "ok", "length_m": 360})
    monkeypatch.setattr(runtime, "HANDLERS", {"calculate_route_length": handler})
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name="calculate_route_length"),
        response(content="Длина — 360 м."),
        response(tool_name="calculate_route_length", call_id="call_2"),
        response(content="Уклон P0–P1 — 3,333 промилле."),
    ]
    messages = [{"role": "system", "content": "Помощник"}]

    first = runtime.answer_question(client, messages, "Какая длина?")
    second = runtime.answer_question(client, messages, "А уклон P0–P1?")

    assert first == "Длина — 360 м."
    assert second == "Уклон P0–P1 — 3,333 промилле."
    assert handler.call_count == 2
    assert [m["content"] for m in messages if m["role"] == "user"] == [
        "Какая длина?", "А уклон P0–P1?",
    ]
    tools = [m for m in messages if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tools] == ["call_1", "call_2"]
    assert json.loads(tools[0]["content"])["length_m"] == 360


@pytest.mark.parametrize(
    "name, arguments",
    [("unknown", "{}"), ("calculate_route_length", "broken json"),
     ("calculate_route_length", "[]"), ("calculate_route_length", '{"extra": 1}')],
)
def test_tool_errors_are_returned_to_model(monkeypatch, name, arguments):
    monkeypatch.setattr(runtime, "HANDLERS", {"calculate_route_length": lambda: {}})
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name=name, arguments=arguments),
        response(content="Не удалось выполнить расчёт."),
    ]
    messages = []

    text = runtime.answer_question(client, messages, "Рассчитай")

    assert text == "Не удалось выполнить расчёт."
    tool = next(m for m in messages if m["role"] == "tool")
    assert json.loads(tool["content"])["status"] == "error"


def test_repeated_tool_calls_are_bounded(monkeypatch):
    monkeypatch.setattr(runtime, "HANDLERS", {"calculate_route_length": lambda: {}})
    client = Mock()
    client.chat.completions.create.return_value = response(tool_name="calculate_route_length")
    messages = []

    text = runtime.answer_question(client, messages, "Рассчитай", max_rounds=2)

    assert client.chat.completions.create.call_count == 2
    assert "превышено" in text
    assert messages[-1] == {"role": "assistant", "content": text}


def test_terminal_accepts_multiple_questions(monkeypatch):
    import main

    monkeypatch.setattr(main, "load_dotenv", lambda path: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(main, "OpenAI", Mock())
    questions = iter(["", "Какая длина?", "А уклон?", "выход"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(questions))
    histories = []

    def answer(client, messages, question):
        histories.append(list(messages))
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": "Ответ"})
        return "Ответ"

    monkeypatch.setattr(main, "answer_question", answer)
    main.main()

    assert len(histories) == 2
    assert histories[0][0]["role"] == "system"
    assert histories[1][-2]["content"] == "Какая длина?"
    assert histories[1][-1]["content"] == "Ответ"


def test_tools_read_updated_input_between_calls(monkeypatch, tmp_path, route_data):
    from core import calculations

    path = tmp_path / "route.json"
    path.write_text(json.dumps(route_data, ensure_ascii=False), encoding="utf-8")
    load_project = calculations.load_project
    monkeypatch.setattr(calculations, "load_project", lambda input_file: load_project(path))
    call_number = 0

    def model_response(**kwargs):
        nonlocal call_number
        call_number += 1
        if call_number == 1:
            return response(tool_name="calculate_route_length")
        if call_number == 2:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["points"][-1]["x"] = 300
            path.write_text(json.dumps(data), encoding="utf-8")
            return response(tool_name="calculate_material_quantities", call_id="call_2")
        if call_number == 4:
            return response(tool_name="calculate_route_length", call_id="call_3")
        return response(content="Ответ")

    client = Mock()
    client.chat.completions.create.side_effect = model_response
    messages = []
    runtime.answer_question(client, messages, "Длина и количество трубы?")
    runtime.answer_question(client, messages, "Пересчитай длину")

    results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
    assert results[0]["length_m"] == 360
    assert results[1]["pipe"]["quantity_m"] == 380
    assert results[2]["length_m"] == 380


def test_levels_tool_is_called_without_arguments(monkeypatch):
    handler = Mock(return_value={"status": "ok", "point_levels": []})
    monkeypatch.setattr(runtime, "HANDLERS", {"calculate_pipe_levels": handler})
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name="calculate_pipe_levels"),
        response(content="Ответ"),
    ]

    runtime.answer_question(client, [], "Глубина в P3?")

    handler.assert_called_once_with()
