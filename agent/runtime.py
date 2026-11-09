import json
import re
from time import perf_counter

from agent.settings import (
    EMPTY_RESPONSE, MAX_TOOL_ROUNDS, MODEL, MODEL_EXTRA_BODY, MISSING_AXIS_REPLY, SOURCE_PREFIX, RELEASE_REFUSAL_PATTERN,
    RELEASE_CLAIM_PATTERN, RELEASE_NEGATION_PATTERN, RELEASE_WARNING_TEMPLATE,
    RELEASE_SUBJECT_PATTERN, RELEASE_SENTENCE_SEPARATOR,
    ROUND_LIMIT_RESPONSE, SOURCE_PATTERN, SOURCE_SEPARATOR,
    SOURCE_WARNING_TEMPLATE, TOOL_LOG_TEMPLATE, TURN_CONTEXT_TEMPLATE,
    USAGE_LOG_TEMPLATE, SESSION_USAGE_TEMPLATE, PRICE_NOTE,
)
from agent.tools import TOOLS
from agent.usage import TokenUsage, utc_now
from core.models import Status, ProblemCode
from config.settings import RELEASE_REFUSED_STATUS


class RouteAgent:
    """Диалог о трассе с историей сообщений, вызовами инструментов и журналом."""

    def __init__(self, client, handlers, system_prompt, model=MODEL,
                 max_rounds=MAX_TOOL_ROUNDS, tool_log=None):
        """Сохраняет клиент, инструменты и настройки, начинает историю системным промптом."""
        self.client, self.handlers = client, handlers
        self.model, self.max_rounds = model, max_rounds
        self.tool_log = [] if tool_log is None else tool_log
        self.usage_log = []
        self.turn = 0
        self.question_usage, self.session_usage = TokenUsage(), TokenUsage()
        self.session_elapsed = 0.0
        self.messages = [{"role": "system", "content": system_prompt}]

    def ask(self, question) -> str:
        """Добавляет вопрос в историю и возвращает ответ после вызовов инструментов."""
        started = perf_counter()
        self.turn += 1
        self.question_usage = TokenUsage()
        self.messages.append({"role": "system", "content": TURN_CONTEXT_TEMPLATE.format(turn=self.turn)})
        self.messages.append({"role": "user", "content": question})
        try:
            return self.answer()
        finally:
            self.log_usage(perf_counter() - started)

    def log_usage(self, elapsed):
        """Печатает итог вопроса и сохраняет его вместе с накопленным итогом сессии."""
        self.session_elapsed += elapsed
        summary = self.question_usage.summary(USAGE_LOG_TEMPLATE, elapsed, turn=self.turn)
        total = self.session_usage.summary(SESSION_USAGE_TEMPLATE, self.session_elapsed)
        self.usage_log.append({"turn": self.turn, "summary": summary, "session_summary": total + "\n\n" + PRICE_NOTE})
        print(summary)

    def answer(self):
        """Получает ответ модели, выполняя инструменты и учитывая каждый ответ API."""
        for _ in range(self.max_rounds):
            response = self.client.chat.completions.create(
                model=self.model, messages=self.messages, tools=TOOLS,
                extra_body=MODEL_EXTRA_BODY,
            )
            usage = getattr(response, "usage", None)
            timestamp = utc_now()
            self.question_usage.add(usage, timestamp)
            self.session_usage.add(usage, timestamp)
            first_choice = response.choices[0]
            message = first_choice.message
            self.messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                text = message.content or EMPTY_RESPONSE
                text = self.missing_axis_reply(text) or text
                self.messages[-1]["content"] = text
                self.check_sources(text)
                self.check_release_claim(text)
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

    def missing_axis_reply(self, text):
        """Подменяет ответ только при отсутствии отказа или имён точек с недостающими отметками."""
        entries = [entry for entry in self.tool_log if entry.get("turn") == self.turn]
        for entry in reversed(entries):
            result = entry.get("result", {})
            if result.get("released") is True:
                return None
            errors = [problem for problem in result.get("problems", []) if problem.get("level") == Status.ERROR]
            missing = [problem for problem in errors if problem.get("code") == ProblemCode.MISSING_AXIS]
            if result.get("status") == Status.ERROR and missing:
                if re.search(RELEASE_REFUSAL_PATTERN, text) and all(
                    re.search(rf"\b{re.escape(problem['where'])}\b", text) for problem in missing
                ):
                    return None
                details = "\n".join(f'{problem["where"]} — {problem["message"]}' for problem in errors)
                return MISSING_AXIS_REPLY.format(
                    status=RELEASE_REFUSED_STATUS, details=details,
                    points=", ".join(problem["where"] for problem in missing), source_prefix=SOURCE_PREFIX,
                    tool=entry["tool"], turn=self.turn,
                )
        return None

    def check_release_claim(self, text):
        """Предупреждает о заявлении выпуска без успешного инструмента в текущем вопросе."""
        claims = [match for sentence in re.split(RELEASE_SENTENCE_SEPARATOR, text)
                  if re.search(RELEASE_SUBJECT_PATTERN, sentence)
                  for match in re.finditer(RELEASE_CLAIM_PATTERN, sentence)
                  if not re.search(RELEASE_NEGATION_PATTERN, sentence[:match.start()])]
        released = any(entry.get("turn") == self.turn and entry.get("result", {}).get("released") is True
                       and entry.get("result", {}).get("status") in (Status.OK, Status.WARNING)
                       for entry in self.tool_log)
        if claims and not released:
            warning = RELEASE_WARNING_TEMPLATE.format(turn=self.turn)
            print(warning)
            self.tool_log.append({"turn": self.turn, "warning": warning})

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
