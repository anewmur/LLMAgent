import json

from agent.settings import MAX_TOOL_ROUNDS, MODEL, MODEL_EXTRA_BODY
from agent.tools import TOOLS
from core.models import Status


class RouteAgent:
    """Диалог о трассе с историей сообщений, вызовами инструментов и журналом."""

    def __init__(self, client, handlers, system_prompt, model=MODEL,
                 max_rounds=MAX_TOOL_ROUNDS, tool_log=None):
        """Сохраняет клиент, инструменты и настройки, начинает историю системным промптом."""
        self.client, self.handlers = client, handlers
        self.model, self.max_rounds = model, max_rounds
        self.tool_log = tool_log
        self.messages = [{"role": "system", "content": system_prompt}]

    def ask(self, question) -> str:
        """Добавляет вопрос в историю и возвращает ответ после вызовов инструментов."""
        self.messages.append({"role": "user", "content": question})
        for _ in range(self.max_rounds):
            response = self.client.chat.completions.create(
                model=self.model, messages=self.messages, tools=TOOLS,
                extra_body=MODEL_EXTRA_BODY,
            )
            first_choice = response.choices[0]
            message = first_choice.message
            self.messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                return message.content or "Модель не вернула текст ответа."
            for call in message.tool_calls:
                self.run_tool(call)

        text = "Не удалось завершить ответ: превышено число обращений к модели."
        self.messages.append({"role": "assistant", "content": text})
        return text

    def run_tool(self, call):
        """Выполняет один инструмент и записывает результат в историю и журнал."""
        try:
            handler = self.handlers[call.function.name]
            args = json.loads(call.function.arguments)
            result = handler(**args)
        except (KeyError, OSError, ValueError, TypeError) as error:
            result = {"status": Status.ERROR, "message": str(error)}
        if self.tool_log is not None:
            self.tool_log.append({"tool": call.function.name, "arguments": call.function.arguments, "result": result})
            print(f"[журнал] {call.function.name}({call.function.arguments}) -> {result.get('status', Status.OK)}")
        self.messages.append({
            "role": "tool", "tool_call_id": call.id,
            "content": json.dumps(result, ensure_ascii=False),
        })
