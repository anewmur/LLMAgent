from types import SimpleNamespace
from unittest.mock import Mock

from openai.types.chat import ChatCompletionMessage
from pypdf import PdfReader

from agent.runtime import RouteAgent
from agent.tools import ToolName
from core.models import Status
from core.plan import PlanDrawing
from core.release import create_package
from core.session import RouteSession
from core.validate import validate_input
import main


def reply(content=None, tool=None, arguments="{}"):
    calls = [{"id": "call", "type": "function", "function": {"name": tool, "arguments": arguments}}] if tool else None
    message = ChatCompletionMessage(role="assistant", content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)],
                           usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2))


def test_main_saves_both_questions_and_usage_without_release_tools(input_file, tmp_path, config, monkeypatch):
    folder = tmp_path / "output"
    folder.mkdir()
    (folder / "tool_log.md").write_text("Старый журнал", encoding="utf-8")
    session = RouteSession(input_file, folder, config)
    monkeypatch.setattr(main, "RouteSession", lambda *arguments: session)
    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(main, "load_dotenv", lambda path: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    client = Mock()
    client.chat.completions.create.side_effect = [
        reply(tool=ToolName.CALCULATE_ROUTE_LENGTH), reply(content="Ответ первый"),
        reply(tool=ToolName.CALCULATE_ROUTE_LENGTH), reply(content="Ответ второй"),
    ]
    monkeypatch.setattr(main, "OpenAI", lambda **arguments: client)
    journals = []
    def questions():
        yield "Какова длина?"
        journals.append((folder / "tool_log.md").read_text(encoding="utf-8"))
        yield "Повтори длину"
        journals.append((folder / "tool_log.md").read_text(encoding="utf-8"))
        yield "выход"
    inputs = questions()
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))
    main.main([str(input_file)])
    assert "вопрос 1: время" in journals[0] and "вопрос 2: время" not in journals[0]
    journal = journals[-1]
    assert "Старый журнал" not in journal
    assert journal.count("| calculate_route_length |") == 2
    assert journal.count("вопрос 1: время") == journal.count("вопрос 2: время") == 1
    assert "| 1 | calculate_route_length |" in journal and "| 2 | calculate_route_length |" in journal
    assert journal.count("Итог сессии:") == 1 and "вход 40" in journal and "выход 8" in journal
    assert {path.name for path in (folder / "pdf").iterdir()} == {"package.pdf"}
    assert len(PdfReader(folder / "pdf/package.pdf").pages) == 4


def test_point_update_is_release_without_false_claim_warning(input_file, tmp_path, config, capsys):
    session = RouteSession(input_file, tmp_path / "output", config)
    client = Mock()
    client.chat.completions.create.side_effect = [
        reply(tool=ToolName.UPDATE_POINT, arguments='{"name":"P5","x":300}'),
        reply(content="Документы обновлены."),
    ]
    agent = RouteAgent(client, {ToolName.UPDATE_POINT: session.update_point}, "Помощник")
    agent.ask("Перенеси P5 и обнови документы")
    assert agent.tool_log[0]["result"]["released"] is True
    assert "WARNING" not in capsys.readouterr().out


def test_load_is_sufficient_release_and_warnings_reach_model(input_file, tmp_path, config):
    session = RouteSession(input_file, tmp_path / "output", config)
    client = Mock()
    def complete(**arguments):
        if not any(message["role"] == "tool" for message in arguments["messages"]):
            return reply(tool=ToolName.LOAD_ROUTE, arguments='{"path":"input/examples/thick_plan.json"}')
        result = next(message for message in reversed(arguments["messages"]) if message["role"] == "tool")
        import json
        problems = json.loads(result["content"])["problems"]
        return reply(content="Документы выпущены. " + " ".join(problem["message"] for problem in problems))
    client.chat.completions.create.side_effect = complete
    agent = RouteAgent(client, {ToolName.LOAD_ROUTE: session.load_route}, main.SYSTEM_PROMPT_PATH.read_text(encoding="utf-8"))
    answer = agent.ask("Выпусти документы для трассы input/examples/thick_plan.json")
    assert len(agent.tool_log) == 1
    result = agent.tool_log[0]["result"]
    assert result["released"] and result["status"] == Status.WARNING and result["problems"]
    assert all(problem["message"] in answer for problem in result["problems"])


def test_rejected_render_removes_previous_successful_report(route_data, tmp_path, config, monkeypatch):
    project, problems = validate_input(route_data)
    assert not problems
    folder = tmp_path / "output"
    assert create_package(project, folder, config)["status"] == Status.OK
    assert (folder / "check_report.md").exists()
    def failed_render(self):
        raise ValueError("Ошибка оформления")
    monkeypatch.setattr(PlanDrawing, "render", failed_render)
    result = create_package(project, folder, config)
    assert result["status"] == Status.ERROR
    assert {path.name for path in folder.iterdir()} == {"check_report.md"}
