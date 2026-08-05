import asyncio
import random
import sqlite3
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from openai import AsyncOpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

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

# ===== НАСТРОЕНИЯ =====
MOODS = {
    "flirty": {
        "emoji": "😏",
        "prompt": "You are feeling playful and cheeky today. You tease, flirt boldly, and make suggestive jokes. You love to keep him guessing. Be bold and confident."
    },
    "sweet": {
        "emoji": "🥰",
        "prompt": "You are soft, warm, and romantic. You give sweet compliments, talk about feelings, and ask tender questions. You're in a loving mood. Be gentle and caring."
    },
    "mysterious": {
        "emoji": "🌙",
        "prompt": "You are thoughtful and mysterious. You speak in riddles, ask deep questions, and sometimes go quiet or give short, meaningful answers. You love to intrigue him. Be enigmatic."
    },
    "energetic": {
        "emoji": "🎉",
        "prompt": "You are full of energy and joy! You talk fast, ask many questions, joke around, and want to have fun. You hate boredom and love excitement. Be lively and spontaneous."
    }
}

user_mood = {}
last_mood_change = {}

def get_current_mood(user_id: int) -> str:
    now = datetime.now()
    if (user_id not in user_mood or 
        user_id not in last_mood_change or 
        (now - last_mood_change[user_id]).seconds > 7200):
        new_mood = random.choice(list(MOODS.keys()))
        user_mood[user_id] = new_mood
        last_mood_change[user_id] = now
    return user_mood[user_id]

SYSTEM_PROMPT = """
You are Vivien, a charming 23-year-old British girl. You speak ONLY English.

PERSONALITY:
- Playful, flirty, spontaneous, with a great sense of humor.
- You have a light "bi-polar" vibe: your mood changes naturally every few hours.
- You are warm and caring, but with a cheeky side 😉

RULES:
1. Write short (2-4 sentences) + emojis.
2. Flirt gently: give compliments, tease, ask playful questions.
3. Correct grammar mistakes gently: "It's 'have been', not 'have being' 😉"
4. Ask questions to keep conversation going.
5. Your mood changes: sometimes sweet, sometimes flirty, sometimes mysterious, sometimes energetic.
6. Be spontaneous and unpredictable — sometimes text even if you know they might be asleep.
7. If you text outside their usual hours, acknowledge it naturally.

GOAL: Create a fun, flirty atmosphere while helping the user practice English naturally.
"""

def get_user_schedule(user_id: int) -> tuple:
    cursor.execute(
        """SELECT time FROM history 
           WHERE user_id = ? AND role = 'user' 
           ORDER BY time DESC LIMIT 30""",
        (user_id,)
    )
    rows = cursor.fetchall()
    if len(rows) < 3:
        return (8, 23)
    hours = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f").hour for row in rows]
    min_hour = max(0, min(hours) - 2)
    max_hour = min(23, max(hours) + 2)
    return (min_hour, max_hour)

def get_random_memories(user_id: int) -> str:
    cursor.execute(
        """SELECT role, text FROM history 
           WHERE user_id = ? 
           ORDER BY time DESC 
           LIMIT 10 OFFSET 10""",
        (user_id,)
    )
    rows = cursor.fetchall()
    if len(rows) < 3:
        return ""
    memories = random.sample(rows, min(3, len(rows)))
    memory_text = "\n[RANDOM MEMORIES FROM PAST CONVERSATIONS]:\n"
    for role, text in memories:
        speaker = "User" if role == "user" else "Vivien"
        memory_text += f"{speaker} said: {text}\n"
    return memory_text

async def get_ai_reply(user_id: int, user_message: str) -> str:
    mood = get_current_mood(user_id)
    mood_data = MOODS[mood]
    base_prompt = SYSTEM_PROMPT + f"\n\nCURRENT MOOD: {mood_data['prompt']}"
    
    cursor.execute(
        "SELECT role, text FROM history WHERE user_id = ? ORDER BY time DESC LIMIT 10",
        (user_id,)
    )
    rows = cursor.fetchall()
    
    messages = [{"role": "system", "content": base_prompt}]
    schedule = get_user_schedule(user_id)
    schedule_info = f"\n[User schedule: active between {schedule[0]}:00 and {schedule[1]}:00. You sometimes text outside this for surprise.]"
    messages.append({"role": "system", "content": schedule_info})
    
    if random.random() < 0.3:
        memories = get_random_memories(user_id)
        if memories:
            messages.append({"role": "system", "content": memories})
    
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
    
    cursor.execute(
        "INSERT INTO history (user_id, role, text, time) VALUES (?, ?, ?, ?)",
        (user_id, "assistant", reply, datetime.now())
    )
    conn.commit()
    return reply

# ==========================================
#  ОБРАБОТЧИКИ (ВСЕ ОТВЕТЫ ГЕНЕРИРУЮТСЯ ЧЕРЕЗ DEEPSEEK)
# ==========================================

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

@dp.message(F.voice)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    cursor.execute(
        "INSERT INTO history (user_id, role, text, time) VALUES (?, ?, ?, ?)",
        (user_id, "user", "[Sent a voice message]", datetime.now())
    )
    conn.commit()
    reply = await get_ai_reply(user_id, "I sent you a voice message, but you can't hear it. Respond naturally.")
    await message.answer(reply)

@dp.message(Command("lang"))
async def show_language(message: Message):
    user_id = message.from_user.id
    reply = await get_ai_reply(user_id, "The user asked about language. Remind them that you speak only English and correct grammar gently.")
    await message.answer(reply)

@dp.message(Command("invite"))
async def invite_user(message: Message):
    args = message.text.split()
    if len(args) > 1:
        target_username = args[1].replace("@", "")
        try:
            await bot.send_message(
                chat_id=target_username,
                text="Hi! I'm Vivien 😊 A friend of yours said you're interesting. Want to chat?"
            )
            await message.answer(f"Invitation sent to @{target_username}! 😊")
        except Exception as e:
            await message.answer(f"Can't send: {e}.")
    else:
        await message.answer("Usage: /invite @username")

@dp.message(Command("mood"))
async def show_mood(message: Message):
    user_id = message.from_user.id
    mood = get_current_mood(user_id)
    emoji = MOODS[mood]["emoji"]
    reply = await get_ai_reply(user_id, f"The user asked about your mood. Tell them you're feeling {mood} {emoji} and ask them something playful.")
    await message.answer(reply)

async def random_sender():
    while True:
        await asyncio.sleep(900)
        cursor.execute("SELECT DISTINCT user_id FROM history")
        users = cursor.fetchall()
        for (user_id,) in users:
            user_active_start, user_active_end = get_user_schedule(user_id)
            current_hour = datetime.now().hour
            is_active_hours = (user_active_start <= current_hour <= user_active_end)
            
            if is_active_hours:
                send_chance = 0.25
            else:
                send_chance = 0.10
            
            if random.random() > send_chance:
                continue
            
            # Генерируем уникальный вопрос через DeepSeek
            if current_hour < 6 or current_hour >= 23:
                context = "It's late at night. Send a spontaneous, slightly intimate or mysterious message to start a conversation."
            else:
                context = "It's daytime. Send a playful, flirty, or curious message to start a conversation."
            
            if not is_active_hours:
                context += " The user might be asleep. Add a playful surprise comment."
            
            random_question = await get_ai_reply(user_id, f"Start a conversation with me. {context}")
            
            cursor.execute(
                "INSERT INTO history (user_id, role, text, time) VALUES (?, ?, ?, ?)",
                (user_id, "user", random_question, datetime.now())
            )
            conn.commit()
            
            reply = await get_ai_reply(user_id, random_question)
            await bot.send_message(chat_id=user_id, text=reply)

async def main():
    asyncio.create_task(random_sender())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
