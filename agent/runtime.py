import json

from agent.tools import TOOLS


def answer_question(client, messages, question, handlers, max_rounds=42, tool_log=None):
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
                handler = handlers[call.function.name]
                args = json.loads(call.function.arguments)
                result = handler(**args)
            except (KeyError, OSError, ValueError, TypeError) as error:
                result = {"status": "error", "message": str(error)}
            if tool_log is not None:
                tool_log.append({"tool": call.function.name, "arguments": call.function.arguments, "result": result})
                print(f"[журнал] {call.function.name}({call.function.arguments}) -> {result.get('status', 'ok')}")
            messages.append({
                "role": "tool", "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    text = "Не удалось завершить ответ: превышено число обращений к модели."
    messages.append({"role": "assistant", "content": text})
    return text
