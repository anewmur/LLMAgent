import os
from argparse import ArgumentParser
from pathlib import Path

from dotenv import load_dotenv
from openai import APIError, OpenAI
import yaml

from agent.runtime import RouteAgent
from agent.settings import BASE_URL, MISSING_API_KEY_MESSAGE, MODEL
from agent.tools import ToolName
from core.models import Status
from core.paths import PROJECT_ROOT
from core.session import RouteSession
from core.settings import INPUT_DIR


INPUT_PATH = INPUT_DIR / "input.json"
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_PATH = PROJECT_ROOT / "config" / "requirements.yaml"
SYSTEM_PROMPT_PATH = PROJECT_ROOT / "agent" / "system_prompt.md"


def load_config():
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def main(argv=None):
    parser = ArgumentParser(description="Диалог о трассе и выпуск комплекта документов.")
    parser.add_argument("input_file", nargs="?", type=Path, default=INPUT_PATH, help="Путь к JSON трассы.")
    arguments = parser.parse_args(argv)
    load_dotenv(PROJECT_ROOT / "api_keys.env")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print(MISSING_API_KEY_MESSAGE)
        return 1
    config = load_config()
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    session = RouteSession(arguments.input_file, OUTPUT_DIR, config)
    initial = session.release()
    if initial["status"] == Status.ERROR:
        print("Начальный выпуск не выполнен:", initial.get("problems") or initial.get("message"))
    handlers = {
        ToolName.CALCULATE_ROUTE_LENGTH: session.calculate_route_length,
        ToolName.CALCULATE_PIPE_LEVELS: session.calculate_pipe_levels,
        ToolName.CALCULATE_MATERIAL_QUANTITIES: session.calculate_material_quantities,
        ToolName.CHANGE_PROFILE_FONT: session.change_profile_font,
        ToolName.UPDATE_POINT: session.update_point,
        ToolName.UPDATE_PIPE: session.update_pipe,
        ToolName.ADD_POINT: session.add_point,
        ToolName.REMOVE_POINT: session.remove_point,
        ToolName.ADD_BEND: session.add_bend,
        ToolName.REMOVE_BEND: session.remove_bend,
        ToolName.LOAD_ROUTE: session.load_route,
        ToolName.RELEASE_DOCUMENTS: session.release,
    }
    client = OpenAI(
        api_key=api_key,
        base_url=BASE_URL,
    )
    agent = RouteAgent(client, handlers, system_prompt, model=MODEL,
                       tool_log=session.tool_log)
    session.usage_log = agent.usage_log
    try:
        run_dialogue(agent)
    finally:
        session.save_tool_log()


def run_dialogue(agent):
    """Читает вопросы до выхода, сохраняя диалог в одном экземпляре агента."""
    print("Задайте вопрос о трассе. Для завершения введите «выход».")

    while True:
        try:
            question = input("\nВы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДиалог завершён.")
            break
        if question.lower() in {"выход", "exit", "quit"}:
            break
        if not question:
            continue

        try:
            answer = agent.ask(question)
        except APIError:
            print("Агент: Не удалось получить ответ модели. Результаты выполненных инструментов сохранены.")
            continue
        print(f"\nАгент: {answer}")


if __name__ == "__main__":
    raise SystemExit(main())
