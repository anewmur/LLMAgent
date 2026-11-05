import os
from pathlib import Path

from dotenv import load_dotenv
from openai import APIError, OpenAI

from agent.runtime import answer_question


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
    "Прочностные расчёты, изменение данных и выпуск документов недоступны. "
    "Не заявляй об их выполнении."
)


def main():
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

        turn_messages = list(messages)
        try:
            answer = answer_question(client, turn_messages, question)
        except APIError:
            print("Агент: Не удалось получить ответ модели.")
            continue
        messages = turn_messages
        print(f"\nАгент: {answer}")


if __name__ == "__main__":
    main()
