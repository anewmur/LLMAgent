# Имя модели DeepSeek, используемой для диалога и выбора инструментов.
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
# Адрес OpenAI-совместимого API DeepSeek.
BASE_URL = "https://api.deepseek.com"
# Подсказка при запуске без ключа API; выводится перед завершением с кодом 1.
MISSING_API_KEY_MESSAGE = (
    "Не задан DEEPSEEK_API_KEY. Скопируйте api_keys.env.example в api_keys.env и укажите ключ "
    "или задайте переменную окружения DEEPSEEK_API_KEY."
)
# Предел последовательных раундов обращения к модели при вызовах инструментов в одном ответе.
MAX_TOOL_ROUNDS = 10
# Отключение режима рассуждений при запросах к модели; прежние параметры API.
MODEL_EXTRA_BODY = {"thinking": {"type": "disabled"}}

# Префикс и формат записи вызова инструмента в консольном журнале.
LOG_PREFIX = "[журнал]"
TOOL_LOG_TEMPLATE = LOG_PREFIX + " вопрос {turn}: {tool}({arguments}) -> {status}"
USAGE_LOG_TEMPLATE = (
    LOG_PREFIX + " вопрос {turn}: время {elapsed} с, токены вход {input_tokens} "
    "(кэш {cache_tokens}) / выход {output_tokens}, стоимость ${cost}"
)
SESSION_USAGE_TEMPLATE = (
    "Итог сессии: время {elapsed} с, токены вход {input_tokens} "
    "(кэш {cache_tokens}) / выход {output_tokens}, стоимость ${cost}"
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
    "При ошибке проект и документы не меняются; уточни данные у пользователя. "
    "При warning изменение принято и комплект опубликован; сообщи предупреждения."
)
BEND_ANGLE_DESCRIPTION = "Угол отвода в градусах из сообщения проверки."
BENDS_DESCRIPTION = (
    "Все отводы, которых требует перенос, из сообщений проверки: и новые отводы, "
    "и новые углы существующих — в одном вызове. at — имя точки, angle_deg — угол в градусах."
)
