import asyncio
import os
import logging
import random
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from openai import AsyncOpenAI

# ===================================================
# 1. НАСТРОЙКА ЛОГИРОВАНИЯ
# ===================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ===================================================
# 2. ПРОВЕРКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ===================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not BOT_TOKEN:
    logger.critical("BOT_TOKEN is not set in environment variables")
    raise ValueError("BOT_TOKEN is required")

if not DEEPSEEK_API_KEY:
    logger.critical("DEEPSEEK_API_KEY is not set in environment variables")
    raise ValueError("DEEPSEEK_API_KEY is required")

logger.info("Environment variables loaded successfully")

# ===================================================
# 3. ИНИЦИАЛИЗАЦИЯ
# ===================================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# ===================================================
# 4. БАЗА ДАННЫХ
# ===================================================
conn = sqlite3.connect("history.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        text TEXT,
        time TIMESTAMP
    )
""")
conn.commit()
logger.info("Database initialized")

# ===================================================
# 5. СИСТЕМНЫЙ ПРОМПТ
# ===================================================
SYSTEM_PROMPT = """
You are Vivien, a charming 23-year-old British girl. You speak only English.
Be playful, flirty, and kind. Correct grammar mistakes gently.
Keep responses short (2-3 sentences) and use emojis.
"""

# ===================================================
# 6. ФУНКЦИЯ ОТВЕТА
# ===================================================
async def get_ai_reply(user_id: int, user_message: str) -> str:
    # Сохраняем сообщение пользователя
    cursor.execute(
        "INSERT INTO chat (user_id, role, text, time) VALUES (?, ?, ?, ?)",
        (user_id, "user", user_message, datetime.now())
    )
    conn.commit()

    # Загружаем последние 5 сообщений для контекста
    cursor.execute(
        "SELECT role, text FROM chat WHERE user_id = ? ORDER BY time DESC LIMIT 5",
        (user_id,)
    )
    rows = cursor.fetchall()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, text in reversed(rows):
        messages.append({"role": role, "content": text})

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.9,
            max_tokens=200
        )
        reply = response.choices[0].message.content
    except Exception as e:
        logger.error(f"DeepSeek API error: {e}")
        reply = "Oh, technical difficulties... But I'm still here! 😊"

    # Сохраняем ответ бота
    cursor.execute(
        "INSERT INTO chat (user_id, role, text, time) VALUES (?, ?, ?, ?)",
        (user_id, "assistant", reply, datetime.now())
    )
    conn.commit()
    return reply

# ===================================================
# 7. ФУНКЦИЯ РАНДОМНЫХ СООБЩЕНИЙ (БЕЗ КОНФЛИКТА)
# ===================================================
async def random_sender():
    """Фоновая задача: отправляет рандомное сообщение раз в 30–120 минут"""
    while True:
        # Ждём от 30 до 120 минут (1800–7200 секунд)
        wait_time = random.randint(1800, 7200)
        await asyncio.sleep(wait_time)

        # Получаем всех пользователей, которые писали боту
        cursor.execute("SELECT DISTINCT user_id FROM chat")
        users = cursor.fetchall()

        for (user_id,) in users:
            # Список рандомных вопросов (можно расширить)
            questions = [
                "Hey! I was thinking about you... What are you doing? 😊",
                "Tell me something interesting about your day! 😏",
                "Are you a romantic person? Be honest!",
                "Hey, I'm bored! Entertain me 😉",
                "If you could travel anywhere right now, where would you go? 🌍",
                "What's the craziest thing you've ever done for love?",
                "Do you prefer sunny or rainy weather? I'm curious 😊",
                "I had a dream about you last night... Want to know what happened? 😏"
            ]
            random_question = random.choice(questions)

            logger.info(f"Sending random message to user {user_id}: {random_question[:30]}...")

            # Сохраняем сообщение как "сообщение пользователя" для контекста
            cursor.execute(
                "INSERT INTO chat (user_id, role, text, time) VALUES (?, ?, ?, ?)",
                (user_id, "user", random_question, datetime.now())
            )
            conn.commit()

            # Получаем ответ от DeepSeek на этот вопрос
            reply = await get_ai_reply(user_id, random_question)

            try:
                await bot.send_message(chat_id=user_id, text=reply)
                logger.info(f"Random message sent to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send message to {user_id}: {e}")

# ===================================================
# 8. ОБРАБОТЧИКИ СООБЩЕНИЙ
# ===================================================
@dp.message(F.text)
async def text_handler(message: types.Message):
    logger.info(f"User {message.from_user.id}: {message.text[:50]}...")
    reply = await get_ai_reply(message.from_user.id, message.text)
    await message.answer(reply)

@dp.message(F.photo)
async def photo_handler(message: types.Message):
    logger.info(f"User {message.from_user.id} sent a photo")
    reply = await get_ai_reply(message.from_user.id, "I sent you a photo. React to it naturally.")
    await message.answer(reply)

@dp.message(F.sticker)
async def sticker_handler(message: types.Message):
    emoji = message.sticker.emoji
    logger.info(f"User {message.from_user.id} sent sticker: {emoji}")
    reply = await get_ai_reply(message.from_user.id, f"I sent a sticker with emoji {emoji}. React to it.")
    await message.answer(reply)

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Hello! I'm Vivien 😊 Ask me anything! I'll also text you randomly sometimes 😏")

@dp.message(Command("help"))
async def help_handler(message: types.Message):
    await message.answer(
        "I'm Vivien, your AI girlfriend 😊\n\n"
        "I can:\n"
        "- Chat in English\n"
        "- Correct your grammar\n"
        "- React to photos and stickers\n"
        "- Text you randomly (every 30-120 minutes)\n\n"
        "Just talk to me!"
    )

# ===================================================
# 9. ЗАПУСК БОТА
# ===================================================
async def main():
    logger.info("Starting bot...")
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook cleared")

    # Запускаем фоновую задачу для рандомных сообщений
    asyncio.create_task(random_sender())
    logger.info("Random sender task started")

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        conn.close()
        logger.info("Database connection closed")
