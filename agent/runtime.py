import json

from agent.tools import HANDLERS, TOOLS


def answer_question(client, messages, question, max_rounds=42):
    messages.append({"role": "user", "content": question})
    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model="deepseek-flash", messages=messages, tools=TOOLS,
            extra_body={"thinking": {"type": "disabled"}},
        )
        first_choice = response.choices[0]
        message = first_choice.message
        messages.append(message.model_dump(exclude_none=True))
        if not message.tool_calls:
            return message.content or "Модель не вернула текст ответа."

        for call in message.tool_calls:
            try:
                handler = HANDLERS[call.function.name]
                args = json.loads(call.function.arguments)
                result = handler(**args)
            except (KeyError, OSError, ValueError, TypeError) as error:
                result = {"status": "error", "message": str(error)}
            messages.append({
                "role": "tool", "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    text = "Не удалось завершить ответ: превышено число обращений к модели."
    messages.append({"role": "assistant", "content": text})
    return text
