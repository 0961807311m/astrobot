import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
from openai import OpenAI

# Логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Змінні (Додайте GROQ_API_KEY у Render -> Environment)
TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Клієнт Groq (працює через бібліотеку openai)
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_KEY
)

def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT);")
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ БД підключена")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

async def ask_ai(prompt: str):
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ти корисний асистент. Відповідай українською мовою."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return "⚠️ ШІ зараз перевантажений. Спробуйте через хвилину."

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🚀 Бот запущений через Groq API! Напиши мені щось.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    response = await ask_ai(message.text)
    await message.answer(response)

async def handle_ping(request):
    return web.Response(text="OK")

async def main():
    init_db()
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🚀 Бот онлайн!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
