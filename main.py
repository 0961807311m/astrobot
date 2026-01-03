import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
import google.generativeai as genai

# Налаштування логів
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Конфігурація ШІ
genai.configure(api_key=GEMINI_KEY)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Функція вибору живої моделі
async def ask_gemini(prompt: str):
    # Пробуємо спочатку 1.5 Flash (найстабільніша)
    # Якщо хочете 2.0, замініть назву на 'gemini-2.0-flash-exp'
    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro']
    
    for model_name in models_to_try:
        try:
            logging.info(f"🤖 Спроба моделі: {model_name}")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text
        except Exception as e:
            logging.error(f"⚠️ Помилка {model_name}: {str(e)[:50]}")
            continue
            
    return "⏳ ШІ перевантажений запитами. Спробуйте пізніше."

# База даних Neon
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT);")
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ База даних підключена")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🚀 Бот активний! Я використовую стабільну версію Gemini 1.5.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    response = await ask_gemini(message.text)
    await message.answer(response)

# Веб-сервер для Render
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
    logging.info("🚀 Полінг запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
