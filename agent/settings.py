# Модель по умолчанию; переопределяется переменной окружения LLM_MODEL.
MODEL = "deepseek-flash"
# USD за 1 млн токенов deepseek-flash, тарифы PEAK и OFF-PEAK.
# Проверено 2026-11-09: https://api-docs.deepseek.com/quick_start/pricing/
PRICE_INPUT_CACHE_HIT_PER_M = 0.006
PRICE_INPUT_CACHE_MISS_PER_M = 0.30
PRICE_OUTPUT_PER_M = 1.20
PRICE_INPUT_CACHE_HIT_OFF_PEAK_PER_M = 0.003
PRICE_INPUT_CACHE_MISS_OFF_PEAK_PER_M = 0.15
PRICE_OUTPUT_OFF_PEAK_PER_M = 0.60
# Интервалы пика UTC: начало включается, конец исключается; только пн–пт.
PEAK_HOURS_UTC = ((1, 4), (6, 10))
PEAK_WEEKDAYS = (0, 1, 2, 3, 4)
TOKENS_PER_PRICE_UNIT = 1_000_000
PRICE_NOTE = "Стоимость по тарифу DeepSeek на момент запроса (пик/вне пика); китайские праздники не учитываются."
# Формулировки стоимости для модели с заданным тарифом и для остальных моделей.
COST_TEMPLATE = "стоимость ${cost}"
UNPRICED_COST_MESSAGE = f"стоимость не рассчитана: тарифы заданы только для {MODEL}"
# Адрес OpenAI-совместимого API по умолчанию; переопределяется LLM_BASE_URL.
BASE_URL = "https://api.deepseek.com"
# Подсказка при запуске без ключа API; выводится перед завершением с кодом 1.
MISSING_API_KEY_MESSAGE = (
    "Не задан LLM_API_KEY. Задайте переменную окружения LLM_API_KEY или создайте в папке запуска "
    "файл api_keys.env со строкой LLM_API_KEY=ваш_ключ."
)
# Предел последовательных раундов обращения к модели при вызовах инструментов в одном ответе.
MAX_TOOL_ROUNDS = 10
# Отключение рассуждений только для адреса DeepSeek по умолчанию.
MODEL_EXTRA_BODY = {"thinking": {"type": "disabled"}}
# Одинаковая строка выбора модели в консоли и в шапке журнала.
MODEL_INFO_TEMPLATE = "Модель: {model}; API: {base_url}"

# Префикс и формат записи вызова инструмента в консольном журнале.
LOG_PREFIX = "[журнал]"
TOOL_LOG_TEMPLATE = LOG_PREFIX + " вопрос {turn}: {tool}({arguments}) -> {status}"
USAGE_LOG_TEMPLATE = (
    LOG_PREFIX + " вопрос {turn}: время {elapsed} с, токены вход {input_tokens} "
    "(кэш {cache_tokens}) / выход {output_tokens}, {cost}"
)
SESSION_USAGE_TEMPLATE = (
    "Итог сессии: время {elapsed} с, токены вход {input_tokens} "
    "(кэш {cache_tokens}) / выход {output_tokens}, {cost}"
)
# Строка источника, разделитель списка инструментов и шаблон извлечения списка с номером вопроса.
SOURCE_PREFIX = "Источник:"
SOURCE_SEPARATOR = ","
SOURCE_PATTERN = (
    SOURCE_PREFIX + rf"\s*<?([\w-]+(?:\s*{SOURCE_SEPARATOR}\s*[\w-]+)*)>?\s*\(вопрос\s+(\d+)\)"
)
# Предупреждение об отсутствии вызова инструмента в указанном вопросе журнала.
SOURCE_WARNING_TEMPLATE = LOG_PREFIX + " предупреждение: источник {source} (вопрос {turn}) не вызывался"
# Номер текущего вопроса передаётся модели, чтобы она могла указать его в источнике.
TURN_CONTEXT_TEMPLATE = "Текущий вопрос: {turn}."

# Ответы при отсутствии текста модели и исчерпании раундов обращения к ней.
EMPTY_RESPONSE = "Модель не вернула текст ответа."
ROUND_LIMIT_RESPONSE = "Не удалось завершить ответ: превышено число обращений к модели."

# Общие правила ответа для инструментов изменения трассы.
EDIT_TOOL_RULES = (
    "При ошибке комплект не выпущен: сообщи причины из problems и уточни данные у пользователя. "
    "При warning изменение принято и комплект опубликован; сообщи предупреждения."
)
BEND_ANGLE_DESCRIPTION = "Угол отвода в градусах из сообщения проверки."
BENDS_DESCRIPTION = (
    "Все отводы, которых требует перенос, из сообщений проверки: и новые отводы, "
    "и новые углы существующих — в одном вызове. at — имя точки, angle_deg — угол в градусах."
)

# Слова о завершённом выпуске; проверяется released=True в результате любого инструмента текущего вопроса.
RELEASE_CLAIM_PATTERN = r"(?i)\b(?:выпущен[а-яё]*|обновл[её]н[а-яё]*|выпустил[а-яё]*|обновил[а-яё]*)\b"
RELEASE_NEGATION_PATTERN = r"(?i)(?:не|будут|будет|буду|будем)\s+(?:был[аио]?\s+)?$"
RELEASE_SUBJECT_PATTERN = r"(?i)\b(?:документ[а-яё]*|комплект)\b"
RELEASE_SENTENCE_SEPARATOR = r"[.!?\n]"
# Явный отказ в выпуске в ответе модели; без него уточнение отметок дополняется защитным шаблоном.
RELEASE_REFUSAL_PATTERN = r"(?i)\bне\s+выпущен[а-яё]*\b"
RELEASE_WARNING_TEMPLATE = LOG_PREFIX + " WARNING: вопрос {turn}: заявлен выпуск без подтверждённого выпуска в этом вопросе"

# Ответ при заблокированном выпуске из-за отметок; значения берутся только из ошибок инструмента.
MISSING_AXIS_REPLY = (
    "{status}.\n{details}\nЗадайте отметки оси для точек: {points}.\n"
    "{source_prefix} {tool} (вопрос {turn})"
)
