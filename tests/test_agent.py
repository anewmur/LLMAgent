import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai.types.chat import ChatCompletionMessage

from agent import runtime
from core.session import RouteSession


def response(content=None, tool_name=None, arguments="{}", call_id="call_1"):
    calls = None
    if tool_name:
        calls = [{"id": call_id, "type": "function", "function": {"name": tool_name, "arguments": arguments}}]
    message = ChatCompletionMessage(role="assistant", content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_questions_preserve_history_and_log_tools():
    handler = Mock(return_value={"status": "ok", "length_m": 360})
    handlers, log = {"calculate_route_length": handler}, []
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name="calculate_route_length"), response(content="Длина — 360 м."),
        response(tool_name="calculate_route_length", call_id="call_2"), response(content="Уклон — 3,33 промилле."),
    ]
    messages = [{"role": "system", "content": "Помощник"}]
    assert runtime.answer_question(client, messages, "Длина?", handlers, tool_log=log) == "Длина — 360 м."
    assert runtime.answer_question(client, messages, "А уклон?", handlers, tool_log=log) == "Уклон — 3,33 промилле."
    assert handler.call_count == len(log) == 2
    assert [m["content"] for m in messages if m["role"] == "user"] == ["Длина?", "А уклон?"]
    assert [m["tool_call_id"] for m in messages if m["role"] == "tool"] == ["call_1", "call_2"]
    assert log[0]["result"]["length_m"] == 360


@pytest.mark.parametrize("name, arguments", [("unknown", "{}"), ("calculate_route_length", "broken json"),
                                             ("calculate_route_length", "[]"), ("calculate_route_length", '{"extra": 1}')])
def test_tool_errors_are_returned_to_model(name, arguments):
    client = Mock()
    client.chat.completions.create.side_effect = [response(tool_name=name, arguments=arguments), response(content="Ошибка расчёта.")]
    messages = []
    assert runtime.answer_question(client, messages, "Рассчитай", {"calculate_route_length": lambda: {}}) == "Ошибка расчёта."
    tool = next(m for m in messages if m["role"] == "tool")
    assert json.loads(tool["content"])["status"] == "error"


def test_repeated_tool_calls_are_bounded():
    client = Mock()
    client.chat.completions.create.return_value = response(tool_name="calculate_route_length")
    messages = []
    text = runtime.answer_question(client, messages, "Рассчитай", {"calculate_route_length": lambda: {}}, max_rounds=2)
    assert client.chat.completions.create.call_count == 2
    assert "превышено" in text and messages[-1] == {"role": "assistant", "content": text}


def test_terminal_accepts_multiple_questions(monkeypatch):
    import main
    session = Mock()
    session.release.return_value = {"status": "ok"}
    session.tool_log = []
    monkeypatch.setattr(main, "RouteSession", lambda: session)
    monkeypatch.setattr(main, "load_dotenv", lambda path: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(main, "OpenAI", Mock())
    questions = iter(["", "Длина?", "А уклон?", "выход"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(questions))
    histories = []

    def answer(client, messages, question, handlers, **kwargs):
        histories.append(list(messages))
        messages.extend([{"role": "user", "content": question}, {"role": "assistant", "content": "Ответ"}])
        return "Ответ"

    monkeypatch.setattr(main, "answer_question", answer)
    main.main()
    assert len(histories) == 2
    assert histories[0][0]["role"] == "system"
    assert histories[1][-2]["content"] == "Длина?"
    session.release.assert_called_once_with()


def test_tools_update_current_session(input_file, tmp_path):
    original = input_file.read_bytes()
    session = RouteSession(input_file, tmp_path / "output")
    handlers = {"calculate_route_length": session.calculate_route_length, "update_point": session.update_point,
                "calculate_material_quantities": session.calculate_material_quantities}
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name="calculate_route_length"),
        response(tool_name="update_point", arguments='{"name":"P5","x":300}', call_id="call_2"),
        response(tool_name="calculate_material_quantities", call_id="call_3"), response(content="Длина стала 380 м."),
    ]
    messages = []
    text = runtime.answer_question(client, messages, "Перенеси P5 на X=300", handlers, tool_log=session.tool_log)
    results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
    assert results[0]["length_m"] == 360
    assert results[1]["status"] == "ok"
    assert results[2]["pipe"]["quantity_m"] == 380
    assert text == "Длина стала 380 м."
    assert len(session.tool_log) == 3 and session.tool_log[1]["tool"] == "update_point"
    assert input_file.read_bytes() == original


@pytest.mark.parametrize("case", ["missing_z", "material_conflict"])
def test_validation_error_is_given_to_model_for_clarification(input_file, tmp_path, case):
    session = RouteSession(input_file, tmp_path / "output")
    if case == "material_conflict":
        session.project.pipe.material = "ПЭ 80"
    before = session.project.model_dump()
    arguments = '{"name":"P3","z":null}' if case == "missing_z" else '{"name":"P5","x":300}'
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name="update_point", arguments=arguments),
        response(content="Какие исходные данные считать правильными?"),
    ]
    messages = []
    text = runtime.answer_question(client, messages, "Удали отметку P3", {"update_point": session.update_point}, tool_log=session.tool_log)
    result = json.loads(next(m["content"] for m in messages if m["role"] == "tool"))
    assert result["status"] == "error" and result["problems"][0]["where"] == ("P3" if case == "missing_z" else "pipe")
    assert text.endswith("?") and session.project.model_dump() == before
    assert not session.changes and not (tmp_path / "output").exists()


def test_levels_tool_is_called_without_arguments():
    handler = Mock(return_value={"status": "ok", "point_levels": []})
    client = Mock()
    client.chat.completions.create.side_effect = [response(tool_name="calculate_pipe_levels"), response(content="Ответ")]
    runtime.answer_question(client, [], "Глубина в P3?", {"calculate_pipe_levels": handler})
    handler.assert_called_once_with()
