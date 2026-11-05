import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from agent.tools import TOOLS, HANDLERS
import json

load_dotenv(Path(__file__).resolve().parent/ "api_keys.env")

api_key = os.environ["DEEPSEEK_API_KEY"]

client = OpenAI(api_key=api_key,
                base_url="https://api.deepseek.com")


messages = [{"role": "user",
             "content": "Рассчитай общую длину трассы из входного файла."}]

while True:
    resp = client.chat.completions.create(
        model="deepseek-flash",
        messages=messages,
        tools=TOOLS,
        extra_body={"thinking": {"type": "disabled"}})

    msg = resp.choices[0].message
    messages.append(msg)              # ответ модели добавляем в историю

    if not msg.tool_calls:            # модель ответила текстом, значит, всё
        print(msg.content)
        break

    for call in msg.tool_calls:       # модель просит вызвать функцию
        func = HANDLERS[call.function.name]
        args = json.loads(call.function.arguments)
        result = func(**args)
        print(f"[журнал] {call.function.name}({args}) -> {result}")
        messages.append({"role": "tool", "tool_call_id": call.id,
                         "content": json.dumps(result)})