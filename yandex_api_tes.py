import os

from openai import OpenAI


API_KEY = os.getenv("YANDEX_API_KEY", 'AQVN164qFPx2CKKmz9OreO_zs9s9FAn4mZ9qz69D')
FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", 'b1grlh2bqatdjmcl9tt0')

if not API_KEY or not FOLDER_ID:
    raise RuntimeError("Set YANDEX_API_KEY and YANDEX_FOLDER_ID before running this script.")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://ai.api.cloud.yandex.net/v1",
)

system_prompt = """
Ты — опытный венчурный партнёр и наставник бизнес-клуба.
Отвечай по-русски, коротко и по делу.
Сначала выдели ключевые риски идеи, потом задай вопросы для усиления проекта.
"""

idea_text = "Хочу сделать ИИ-тренажёр для студентов по бизнес-кейсам и стартап-питчам."
context = """
- Аудитория: студенты и активисты бизнес-клуба
- Ценность: тренировка мышления и самостоятельная подготовка к кейсам
- Цель MVP: рабочее демо для хакатона
"""

response = client.chat.completions.create(
    model=f"gpt://{FOLDER_ID}/yandexgpt-5-pro",
    messages=[
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": f"Разбери идею:\n{idea_text}\n\nКонтекст:\n{context}",
        },
    ],
    temperature=0.6,
    max_tokens=1024,
)

print(response.choices[0].message.content)
