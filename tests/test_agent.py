import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai.types.chat import ChatCompletionMessage

from agent.runtime import RouteAgent
from agent.settings import BASE_URL, MAX_TOOL_ROUNDS, MODEL
from agent.tools import ToolName
from core.session import RouteSession
from main import SYSTEM_PROMPT_PATH


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
    assert [message["content"] for message in messages if message["role"] == "user"] == ["Длина?", "А уклон?"]
    assert [message["tool_call_id"] for message in messages if message["role"] == "tool"] == ["call_1", "call_2"]
    assert log[0]["result"]["length_m"] == 360
    assert agent.turn == 2 and [entry["turn"] for entry in log] == [1, 2]


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


@pytest.mark.parametrize("input_name, exit_signal", [
    (None, None), ("input/examples/route_2.json", None), (None, EOFError), (None, KeyboardInterrupt),
])
def test_terminal_accepts_multiple_questions(monkeypatch, config, input_name, exit_signal):
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
    exit_value = "выход" if exit_signal is None else exit_signal()
    monkeypatch.setattr("builtins.input", Mock(side_effect=["", "Длина?", "А уклон?", exit_value]))
    agent = Mock()
    agent.ask.return_value = "Ответ"
    agent_factory = Mock(return_value=agent)
    monkeypatch.setattr(main, "RouteAgent", agent_factory)
    main.main([] if input_name is None else [input_name])
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
    expected_input = main.INPUT_PATH if input_name is None else main.Path(input_name)
    session_factory.assert_called_once_with(expected_input, main.OUTPUT_DIR, config)
    session.save_tool_log.assert_called_once_with()


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
    assert [entry["turn"] for entry in session.tool_log] == [1, 1, 1]
    assert input_file.read_bytes() == original


@pytest.mark.parametrize("case", ["missing_axis", "material_conflict"])
def test_validation_error_is_given_to_model_for_clarification(input_file, tmp_path, case, config):
    session = RouteSession(input_file, tmp_path / "output", config)
    if case == "material_conflict":
        session.project.pipe.material = "ПЭ 80"
    before = session.project.model_dump()
    arguments = '{"name":"P3","axis":null}' if case == "missing_axis" else '{"name":"P5","x":300}'
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name="update_point", arguments=arguments),
        response(content="Какие исходные данные считать правильными?"),
    ]
    agent = RouteAgent(client, {"update_point": session.update_point}, "Помощник", tool_log=session.tool_log)
    text = agent.ask("Удали отметку P3")
    result = json.loads(next(message["content"] for message in agent.messages if message["role"] == "tool"))
    assert result["status"] == "error" and result["problems"][0]["where"] == ("P3" if case == "missing_axis" else "pipe")
    assert text.endswith("?") and session.project.model_dump() == before
    assert not session.changes and not (tmp_path / "output").exists()


def test_levels_tool_is_called_without_arguments():
    handler = Mock(return_value={"status": "ok", "point_levels": []})
    client = Mock()
    client.chat.completions.create.side_effect = [response(tool_name="calculate_pipe_levels"), response(content="Ответ")]
    RouteAgent(client, {"calculate_pipe_levels": handler}, "Помощник").ask("Глубина в P3?")
    handler.assert_called_once_with()


def test_missing_axis_is_clarified_before_documents_are_released(route_data, write_route, tmp_path, config):
    del route_data["points"][3]["axis"]
    input_file = write_route(route_data)
    original = input_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    before = session.project.model_dump()
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name=ToolName.RELEASE_DOCUMENTS.value),
        response(content="В точке P3 нет отметки оси трубы. Укажите отметку."),
        response(tool_name=ToolName.UPDATE_POINT.value, arguments='{"name":"P3","axis":100.6}', call_id="call_2"),
        response(content="Отметка оси P3: не задана → 100,60 м. Комплект выпущен."),
    ]
    handlers = {ToolName.RELEASE_DOCUMENTS: session.release, ToolName.UPDATE_POINT: session.update_point}
    agent = RouteAgent(client, handlers, SYSTEM_PROMPT_PATH.read_text(encoding="utf-8"), tool_log=session.tool_log)

    assert "нет отметки" in agent.ask("Выпусти комплект документов")
    first = session.tool_log[0]["result"]
    assert first["status"] == "error"
    assert any(problem["where"] == "P3" and "axis" in problem["message"] for problem in first["problems"])
    assert session.project.model_dump() == before and not session.changes
    assert not folder.exists()

    assert "Комплект выпущен" in agent.ask("У P3 отметка оси 100,6 м")
    updated = session.tool_log[1]["result"]
    assert updated["status"] == "ok"
    assert updated["changes"]["values"] == [
        {"name": "P3, отметка оси трубы", "before": None, "after": 100.6, "unit": "м"},
    ]
    assert session.project.points[3].axis == 100.6 and not session.problems
    assert (folder / "pdf/package.pdf").is_file() and (folder / "changes.md").is_file()
    assert [entry["tool"] for entry in session.tool_log] == ["release_documents", "update_point"]
    assert [message["content"] for message in agent.messages if message["role"] == "user"] == [
        "Выпусти комплект документов", "У P3 отметка оси 100,6 м",
    ]
    assert input_file.read_bytes() == original


def test_pipe_tool_updates_session_and_returns_changes(input_file, tmp_path, config):
    original = input_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name=ToolName.UPDATE_PIPE.value, arguments=json.dumps({
            "material": "ПЭ 80", "sdr": 11, "outer_diameter": 160, "wall_thickness": 14.6,
        }, ensure_ascii=False)),
        response(content="Изменения: ПЭ 100 → ПЭ 80; SDR 17 → 11; диаметр 110 → 160 мм; стенка 6,6 → 14,6 мм."),
    ]
    agent = RouteAgent(client, {ToolName.UPDATE_PIPE: session.update_pipe},
                       SYSTEM_PROMPT_PATH.read_text(encoding="utf-8"), tool_log=session.tool_log)

    text = agent.ask("Замени трубу на ПЭ 80 SDR 11, наружный диаметр 160 мм, стенка 14,6 мм")

    result = json.loads(next(message["content"] for message in agent.messages if message["role"] == "tool"))
    assert result["status"] == "ok", result
    assert result["changes"]["values"] == [
        {"name": "Материал трубы", "before": "ПЭ 100", "after": "ПЭ 80", "unit": ""},
        {"name": "Наружный диаметр трубы", "before": 110, "after": 160, "unit": "мм"},
        {"name": "Толщина стенки трубы", "before": 6.6, "after": 14.6, "unit": "мм"},
        {"name": "SDR", "before": 17, "after": 11, "unit": ""},
        {"name": "Материал трубы в описании объекта", "before": "ПЭ 100", "after": "ПЭ 80", "unit": ""},
    ]
    assert result["changes"]["sheets"] == ["Общие данные", "План", "Профиль", "Спецификация"]
    assert session.project.pipe.material == session.project.object.pipe_material == "ПЭ 80"
    assert session.project.pipe.outer_diameter_mm == 160 and session.project.pipe.wall_mm == 14.6
    assert session.project.pipe.sdr == 11
    assert session.tool_log[0]["tool"] == "update_pipe" and session.tool_log[0]["result"] == result
    assert text.startswith("Изменения:") and "ПЭ 100 → ПЭ 80" in text
    assert (folder / "pdf/package.pdf").is_file()
    assert "Материал трубы: **ПЭ 100 → ПЭ 80**." in (folder / "changes.md").read_text(encoding="utf-8")
    assert input_file.read_bytes() == original


@pytest.mark.parametrize("called", [False, True])
def test_source_warning_uses_session_tool_history(called, capsys):
    name = ToolName.CALCULATE_ROUTE_LENGTH.value
    text = f"Длина — 360 м.\nИсточник: {name} (вопрос 1)"
    handler = Mock(return_value={"status": "ok", "length_m": 360})
    client = Mock()
    replies = [response(tool_name=name)] if called else []
    client.chat.completions.create.side_effect = replies + [response(content=text), response(content=text)]
    agent = RouteAgent(client, {name: handler}, "Помощник")

    assert agent.ask("Длина?") == text
    first_output = capsys.readouterr().out
    assert agent.ask("Повтори значение из истории") == text
    second_output = capsys.readouterr().out
    assert agent.turn == 2
    assert agent.messages[1] == {"role": "system", "content": "Текущий вопрос: 1."}
    warnings = [entry for entry in agent.tool_log if "warning" in entry]
    if called:
        handler.assert_called_once_with()
        assert "[журнал] вопрос 1: calculate_route_length({}) -> ok" in first_output
        assert "предупреждение" not in first_output + second_output
        assert not warnings and len(agent.tool_log) == 1
        assert agent.tool_log[0]["turn"] == 1
    else:
        handler.assert_not_called()
        warning = "[журнал] предупреждение: источник calculate_route_length (вопрос 1) не вызывался"
        assert first_output.strip() == second_output.strip() == warning
        assert warnings == [{"turn": 1, "warning": warning}, {"turn": 2, "warning": warning}]


def test_source_with_called_tool_and_wrong_turn_warns(capsys):
    name = ToolName.CALCULATE_ROUTE_LENGTH.value
    text = f"Длина — 360 м.\nИсточник: {name} (вопрос 2)"
    handler = Mock(return_value={"status": "ok", "length_m": 360})
    client = Mock()
    client.chat.completions.create.side_effect = [response(tool_name=name), response(content=text)]
    agent = RouteAgent(client, {name: handler}, "Помощник")

    assert agent.ask("Длина?") == text

    handler.assert_called_once_with()
    assert agent.tool_log[0]["tool"] == name and agent.tool_log[0]["turn"] == 1
    warning = "[журнал] предупреждение: источник calculate_route_length (вопрос 2) не вызывался"
    assert warning in capsys.readouterr().out
    assert agent.tool_log[-1] == {"turn": 1, "warning": warning}


@pytest.mark.parametrize("both_called", [True, False])
def test_multiple_sources_warn_only_about_the_uncalled_tool(both_called, capsys):
    first_name = ToolName.CALCULATE_ROUTE_LENGTH.value
    second_name = ToolName.CALCULATE_MATERIAL_QUANTITIES.value
    text = f"Длина — 360 м.\nИсточник: {first_name},  {second_name} (вопрос 1)"
    handlers = {name: Mock(return_value={"status": "ok"}) for name in [first_name, second_name]}
    replies = [response(tool_name=first_name)]
    if both_called:
        replies.append(response(tool_name=second_name, call_id="call_2"))
    client = Mock()
    client.chat.completions.create.side_effect = replies + [response(content=text)]
    agent = RouteAgent(client, handlers, "Помощник")

    assert agent.ask("Какова длина и сколько нужно трубы?") == text

    handlers[first_name].assert_called_once_with()
    if both_called:
        handlers[second_name].assert_called_once_with()
    else:
        handlers[second_name].assert_not_called()
    warnings = [entry["warning"] for entry in agent.tool_log if "warning" in entry]
    expected = [] if both_called else [f"[журнал] предупреждение: источник {second_name} (вопрос 1) не вызывался"]
    assert warnings == expected
    printed = capsys.readouterr().out.splitlines()
    assert [line for line in printed if "предупреждение:" in line] == expected


def test_agent_clarifies_bend_and_repeats_rejected_point_addition(route_data, write_route, tmp_path, config):
    route_data["points"] = [route_data["points"][0], route_data["points"][2]]
    route_data["bends"] = []
    session = RouteSession(write_route(route_data), tmp_path / "output", config)
    arguments = {"name": "P1a", "after": "P0", "x": 60, "y": 60, "ground": 102.6, "axis": 100.2}
    client = Mock()
    client.chat.completions.create.side_effect = [
        response(tool_name=ToolName.ADD_POINT.value, arguments=json.dumps(arguments)),
        response(content="Точка не добавлена: нужен отвод 90°. Установить его?"),
        response(tool_name=ToolName.ADD_POINT.value, arguments=json.dumps({**arguments, "bend_angle": 90}), call_id="call_2"),
        response(content="Добавлена точка P1a и отвод 90°."),
    ]
    agent = RouteAgent(client, {ToolName.ADD_POINT: session.add_point},
                       SYSTEM_PROMPT_PATH.read_text(encoding="utf-8"), tool_log=session.tool_log)
    assert agent.ask("Добавь P1a после P0: x=60, y=60, земля 102,6, ось трубы 100,2").endswith("?")
    assert all(point.id != "P1a" for point in session.project.points)
    assert session.tool_log[0]["result"]["status"] == "error"
    assert "Добавлена" in agent.ask("Да, установи отвод с предложенным углом")
    assert [point.id for point in session.project.points] == ["P0", "P1a", "P2"]
    assert [(bend.at, bend.angle_deg) for bend in session.project.bends] == [("P1a", 90)]
    assert session.tool_log[1]["result"]["status"] in ("ok", "warning")
