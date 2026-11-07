import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai.types.chat import ChatCompletionMessage

from agent.runtime import RouteAgent
from agent.settings import BASE_URL, MAX_TOOL_ROUNDS, MODEL
from agent.tools import ToolName
from core.session import RouteSession


def response(content=None, tool_name=None, arguments="{}", call_id="call_1"):
    calls = None
    if tool_name:
        calls = [{"id": call_id, "type": "function", "function": {"name": tool_name, "arguments": arguments}}]
    message = ChatCompletionMessage(role="assistant", content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_questions_preserve_history_and_log_tools():
    handler = Mock(return_value={"status": "ok", "length_m": 360})
    handlers, log = {ToolName.CALCULATE_ROUTE_LENGTH: handler}, []
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name="calculate_route_length"), response(content="Длина — 360 м."),
        response(tool_name="calculate_route_length", call_id="call_2"), response(content="Уклон — 3,33 промилле."),
    ]
    agent = RouteAgent(client, handlers, "Помощник", model="test-model", tool_log=log)
    assert agent.ask("Длина?") == "Длина — 360 м."
    assert agent.ask("А уклон?") == "Уклон — 3,33 промилле."
    messages = agent.messages
    assert messages[0] == {"role": "system", "content": "Помощник"}
    assert all(call.kwargs["model"] == "test-model" for call in client.chat.completions.create.call_args_list)
    assert handler.call_count == len(log) == 2
    assert [m["content"] for m in messages if m["role"] == "user"] == ["Длина?", "А уклон?"]
    assert [m["tool_call_id"] for m in messages if m["role"] == "tool"] == ["call_1", "call_2"]
    assert log[0]["result"]["length_m"] == 360


@pytest.mark.parametrize("name, arguments", [("unknown", "{}"), ("calculate_route_length", "broken json"),
                                             ("calculate_route_length", "[]"), ("calculate_route_length", '{"extra": 1}')])
def test_tool_errors_are_returned_to_model(name, arguments):
    client = Mock()
    client.chat.completions.create.side_effect = [response(tool_name=name, arguments=arguments), response(content="Ошибка расчёта.")]
    agent = RouteAgent(client, {"calculate_route_length": lambda: {}}, "Помощник")
    assert agent.ask("Рассчитай") == "Ошибка расчёта."
    tool = next(message for message in agent.messages if message["role"] == "tool")
    assert json.loads(tool["content"])["status"] == "error"


@pytest.mark.parametrize("max_rounds", [None, 2])
def test_repeated_tool_calls_are_bounded(max_rounds):
    client = Mock()
    client.chat.completions.create.return_value = response(tool_name="calculate_route_length")
    options = {} if max_rounds is None else {"max_rounds": max_rounds}
    agent = RouteAgent(client, {"calculate_route_length": lambda: {}}, "Помощник", **options)
    text = agent.ask("Рассчитай")
    assert client.chat.completions.create.call_count == (MAX_TOOL_ROUNDS if max_rounds is None else max_rounds)
    assert "превышено" in text and agent.messages[-1] == {"role": "assistant", "content": text}


def test_terminal_accepts_multiple_questions(monkeypatch, config):
    import main
    session = Mock()
    session.release.return_value = {"status": "ok"}
    session.tool_log = []
    session_factory = Mock(return_value=session)
    config_loader = Mock(return_value=config)
    monkeypatch.setattr(main, "RouteSession", session_factory)
    monkeypatch.setattr(main, "load_config", config_loader)
    monkeypatch.setattr(main, "load_dotenv", lambda path: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    client = Mock()
    client_factory = Mock(return_value=client)
    monkeypatch.setattr(main, "OpenAI", client_factory)
    questions = iter(["", "Длина?", "А уклон?", "выход"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(questions))
    agent = Mock()
    agent.ask.return_value = "Ответ"
    agent_factory = Mock(return_value=agent)
    monkeypatch.setattr(main, "RouteAgent", agent_factory)
    main.main()
    assert [call.args[0] for call in agent.ask.call_args_list] == ["Длина?", "А уклон?"]
    agent_factory.assert_called_once()
    arguments = agent_factory.call_args
    assert arguments.args[0] is client
    assert set(arguments.args[1]) == set(ToolName)
    assert arguments.args[2] == main.SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    assert arguments.kwargs == {"model": MODEL, "tool_log": session.tool_log}
    client_factory.assert_called_once_with(api_key="test-key", base_url=BASE_URL)
    session.release.assert_called_once_with()
    config_loader.assert_called_once_with()
    session_factory.assert_called_once_with(main.INPUT_PATH, main.OUTPUT_DIR, config)


def test_tools_update_current_session(input_file, tmp_path, config):
    original = input_file.read_bytes()
    session = RouteSession(input_file, tmp_path / "output", config)
    handlers = {"calculate_route_length": session.calculate_route_length, "update_point": session.update_point,
                "calculate_material_quantities": session.calculate_material_quantities}
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name="calculate_route_length"),
        response(tool_name="update_point", arguments='{"name":"P5","x":300}', call_id="call_2"),
        response(tool_name="calculate_material_quantities", call_id="call_3"), response(content="Длина стала 380 м."),
    ]
    agent = RouteAgent(client, handlers, "Помощник", tool_log=session.tool_log)
    text = agent.ask("Перенеси P5 на X=300")
    results = [json.loads(message["content"]) for message in agent.messages if message["role"] == "tool"]
    assert results[0]["length_m"] == 360
    assert results[1]["status"] == "ok"
    assert results[2]["pipe"]["quantity_m"] == 380
    assert text == "Длина стала 380 м."
    assert len(session.tool_log) == 3 and session.tool_log[1]["tool"] == "update_point"
    assert input_file.read_bytes() == original


@pytest.mark.parametrize("case", ["missing_z", "material_conflict"])
def test_validation_error_is_given_to_model_for_clarification(input_file, tmp_path, case, config):
    session = RouteSession(input_file, tmp_path / "output", config)
    if case == "material_conflict":
        session.project.pipe.material = "ПЭ 80"
    before = session.project.model_dump()
    arguments = '{"name":"P3","z":null}' if case == "missing_z" else '{"name":"P5","x":300}'
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name="update_point", arguments=arguments),
        response(content="Какие исходные данные считать правильными?"),
    ]
    agent = RouteAgent(client, {"update_point": session.update_point}, "Помощник", tool_log=session.tool_log)
    text = agent.ask("Удали отметку P3")
    result = json.loads(next(message["content"] for message in agent.messages if message["role"] == "tool"))
    assert result["status"] == "error" and result["problems"][0]["where"] == ("P3" if case == "missing_z" else "pipe")
    assert text.endswith("?") and session.project.model_dump() == before
    assert not session.changes and not (tmp_path / "output").exists()


def test_levels_tool_is_called_without_arguments():
    handler = Mock(return_value={"status": "ok", "point_levels": []})
    client = Mock()
    client.chat.completions.create.side_effect = [response(tool_name="calculate_pipe_levels"), response(content="Ответ")]
    RouteAgent(client, {"calculate_pipe_levels": handler}, "Помощник").ask("Глубина в P3?")
    handler.assert_called_once_with()
