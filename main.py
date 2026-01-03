import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
import google.generativeai as genai  # Зміна бібліотеки

# Конфігурація
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Налаштування Gemini
genai.configure(api_key=GEMINI_KEY)
# Використовуємо 1.5 Flash як основну
model = genai.GenerativeModel('gemini-1.5-flash')

bot = Bot(token=TOKEN)
dp = Dispatcher()

# База даних
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT);")
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ БД Neon готова")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# Функція запиту до ШІ
async def ask_gemini(prompt: str):
    try:
        # Старий надійний метод
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text
        return "🤖 ШІ не зміг відповісти."
    except Exception as e:
        logging.error(f"AI Error: {e}")
        if "429" in str(e):
            return "⏳ Ліміт вичерпано. Спробуйте через хвилину."
        return f"⚠️ Помилка ШІ: {str(e)[:50]}"

# Хендлери
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🚀 Бот запущений на стабільній версії!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    ai_response = await ask_gemini(message.text)
    await message.answer(ai_response)

# Веб-сервер
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
