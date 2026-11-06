import os
from pathlib import Path

from dotenv import load_dotenv
from openai import APIError, OpenAI

from agent.runtime import answer_question
from core.session import RouteSession


SYSTEM_PROMPT = (
    "Ты помощник по расчётам трассы трубопровода. "
    "Для каждого нового запроса расчёта вызывай нужные инструменты по их описаниям. "
    "Расчётные значения бери только из результатов инструментов, не вычисляй их сам. "
    "Для вопроса об отдельной точке или участке найди его в результате. "
    "Учитывай историю разговора при уточнениях. "
    "Не придумывай отсутствующие данные и не подменяй неизвестные значения нулём. "
    "Сообщай проблемы понятным языком; причину отсутствующего результата бери из инструмента. "
    "Не делай собственных выводов о влиянии ошибок. "
    "Отвечай кратко, только по вопросу, без названий полей JSON, "
    "описания устройства расчёта и пустых списков замечаний. "
    "Общий статус успеха не означает готовность всей документации. "
    "Положительный уклон означает подъём от начала к концу, отрицательный — спуск. "
    "Глубина рассчитывается до наружного низа трубы. "
    "Для правки точки используй update_point: name — имя, z — отметка оси трубы. "
    "Если пользователь просит удалить отметку, передай z=null. "
    "При ошибке проверки сообщи её причину и задай уточняющий вопрос; изменение не выполнено. "
    "Конфликт материалов нельзя исправить изменением координат точки. "
    "После успешной правки покажи перечень изменений из инструмента. "
    "Для перевыпуска документов без изменения точки используй release_documents. "
    "Состояние трассы хранится в текущей сессии. Прочностные расчёты недоступны."
)


def main():
    session = RouteSession()
    initial = session.release()
    if initial["status"] == "error":
        print("Начальный выпуск не выполнен:", initial.get("problems") or initial.get("message"))
    handlers = {
        "calculate_route_length": session.calculate_route_length,
        "calculate_pipe_levels": session.calculate_pipe_levels,
        "calculate_material_quantities": session.calculate_material_quantities,
        "change_profile_font": session.change_profile_font,
        "update_point": session.update_point,
        "release_documents": session.release,
    }
    load_dotenv(Path(__file__).resolve().parent / "api_keys.env")
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
            answer = answer_question(client, messages, question, handlers, tool_log=session.tool_log)
        except APIError:
            print("Агент: Не удалось получить ответ модели. Результаты выполненных инструментов сохранены.")
            continue
        print(f"\nАгент: {answer}")


if __name__ == "__main__":
    main()
