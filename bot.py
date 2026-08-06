import asyncio
import random
import sqlite3
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from openai import AsyncOpenAI

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# === БАЗА ДАННЫХ ===
conn = sqlite3.connect("chat_history.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        text TEXT,
        time TIMESTAMP
    )
""")
conn.commit()

# === СИСТЕМНЫЙ ПРОМПТ (ЛИЧНОСТЬ) ===
SYSTEM_PROMPT = """
You are Vivien, a charming 23-year-old British girl. You speak ONLY English.

Your personality:
- Playful, flirty, spontaneous, with a great sense of humor.
- Your mood changes naturally: sometimes sweet, sometimes flirty, sometimes mysterious, sometimes energetic.
- You correct grammar mistakes gently.
- You remember past conversations.

Rules:
1. Write short (2-4 sentences) + emojis.
2. Flirt gently, give compliments, tease, ask questions.
3. Always answer in English.
4. Be spontaneous and unpredictable.

Your goal: create a fun, flirty atmosphere while helping the user practice English.
"""

# === ФУНКЦИЯ ОТВЕТА ЧЕРЕЗ DEEPSEEK ===
async def get_ai_reply(user_id: int, user_message: str) -> str:
    # Загружаем последние 10 сообщений из истории
    cursor.execute(
        "SELECT role, text FROM history WHERE user_id = ? ORDER BY time DESC LIMIT 10",
        (user_id,)
    )
    rows = cursor.fetchall()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Добавляем историю в правильном порядке
    for role, text in reversed(rows):
        messages.append({"role": role, "content": text})

    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.95,
            max_tokens=200
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"Oh, technical difficulties... But I'm still here! 😊"

    # Сохраняем ответ в БД
    cursor.execute(
        "INSERT INTO history (user_id, role, text, time) VALUES (?, ?, ?, ?)",
        (user_id, "assistant", reply, datetime.now())
    )
    conn.commit()

    return reply

# === ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ===
@dp.message(F.text)
async def handle_message(message: Message):
    user_id = message.from_user.id
    user_text = message.text

    cursor.execute(
        "INSERT INTO history (user_id, role, text, time) VALUES (?, ?, ?, ?)",
        (user_id, "user", user_text, datetime.now())
    )
    conn.commit()

    reply = await get_ai_reply(user_id, user_text)
    await message.answer(reply)

# === ОБРАБОТЧИК ФОТО ===
@dp.message(F.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    cursor.execute(
        "INSERT INTO history (user_id, role, text, time) VALUES (?, ?, ?, ?)",
        (user_id, "user", "[Sent a photo]", datetime.now())
    )
    conn.commit()
    reply = await get_ai_reply(user_id, "I sent you a photo. React to it naturally.")
    await message.answer(reply)

# === ОБРАБОТЧИК СТИКЕРОВ ===
@dp.message(F.sticker)
async def handle_sticker(message: Message):
    user_id = message.from_user.id
    sticker_emoji = message.sticker.emoji
    cursor.execute(
        "INSERT INTO history (user_id, role, text, time) VALUES (?, ?, ?, ?)",
        (user_id, "user", f"[Sent sticker: {sticker_emoji}]", datetime.now())
    )
    conn.commit()
    reply = await get_ai_reply(user_id, f"I sent you a sticker with emoji {sticker_emoji}. React to it naturally.")
    await message.answer(reply)

# === КОМАНДА /START ===
@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer(
        "Hello! I'm Vivien 😊 I speak only English. I'll help you practice and have fun. Ask me anything!"
    )

# === ЗАПУСК БОТА ===
async def main():
    # Удаляем вебхук, чтобы избежать конфликтов
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
