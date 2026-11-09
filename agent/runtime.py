import json
import re

from agent.settings import (
    EMPTY_RESPONSE, MAX_TOOL_ROUNDS, MODEL, MODEL_EXTRA_BODY,
    ROUND_LIMIT_RESPONSE, SOURCE_PATTERN, SOURCE_SEPARATOR,
    SOURCE_WARNING_TEMPLATE, TOOL_LOG_TEMPLATE, TURN_CONTEXT_TEMPLATE,
)
from agent.tools import TOOLS
from core.models import Status


class RouteAgent:
    """Диалог о трассе с историей сообщений, вызовами инструментов и журналом."""

    def __init__(self, client, handlers, system_prompt, model=MODEL,
                 max_rounds=MAX_TOOL_ROUNDS, tool_log=None):
        """Сохраняет клиент, инструменты и настройки, начинает историю системным промптом."""
        self.client, self.handlers = client, handlers
        self.model, self.max_rounds = model, max_rounds
        self.tool_log = [] if tool_log is None else tool_log
        self.turn = 0
        self.messages = [{"role": "system", "content": system_prompt}]

    def ask(self, question) -> str:
        """Добавляет вопрос в историю и возвращает ответ после вызовов инструментов."""
        self.turn += 1
        self.messages.append({"role": "system", "content": TURN_CONTEXT_TEMPLATE.format(turn=self.turn)})
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
                text = message.content or EMPTY_RESPONSE
                self.check_sources(text)
                return text
            for call in message.tool_calls:
                self.run_tool(call)

        text = ROUND_LIMIT_RESPONSE
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
        self.tool_log.append({"turn": self.turn, "tool": call.function.name,
                              "arguments": call.function.arguments, "result": result})
        print(TOOL_LOG_TEMPLATE.format(turn=self.turn, tool=call.function.name,
                                       arguments=call.function.arguments, status=result.get("status", Status.OK)))
        self.messages.append({
            "role": "tool", "tool_call_id": call.id,
            "content": json.dumps(result, ensure_ascii=False),
        })

    def check_sources(self, text):
        """Предупреждает, если инструмент не вызывался в указанном вопросе."""
        for sources, turn_text in re.findall(SOURCE_PATTERN, text):
            source_turn = int(turn_text)
            for source_name in sources.split(SOURCE_SEPARATOR):
                source = source_name.strip()
                if not any(entry.get("tool") == source and entry.get("turn") == source_turn for entry in self.tool_log):
                    warning = SOURCE_WARNING_TEMPLATE.format(source=source, turn=source_turn)
                    print(warning)
                    self.tool_log.append({"turn": self.turn, "warning": warning})
