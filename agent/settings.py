# Имя модели DeepSeek, используемой для диалога и выбора инструментов.
MODEL = "deepseek-flash"
# Адрес OpenAI-совместимого API DeepSeek.
BASE_URL = "https://api.deepseek.com"
# Предел последовательных раундов обращения к модели при вызовах инструментов в одном ответе.
MAX_TOOL_ROUNDS = 10
# Отключение режима рассуждений при запросах к модели; прежние параметры API.
MODEL_EXTRA_BODY = {"thinking": {"type": "disabled"}}
