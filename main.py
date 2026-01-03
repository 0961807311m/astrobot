import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
from google import genai

# ==========================================
# ⚙️ КОНФІГУРАЦІЯ
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_KEY)

# ==========================================
# 🗄️ БАЗА ДАНИХ NEON
# ==========================================
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Приклад створення таблиці користувачів
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ База даних Neon підключена успішно")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# ==========================================
# 🌐 ВЕБ-СЕРВЕР (Keep-Alive для Render)
# ==========================================
async def handle_ping(request):
    return web.Response(text="WorkDays Bot is Online!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render використовує порт 10000
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logging.info("✅ Веб-сервер на порту 10000 запущено")

# ==========================================
# 🧠 ЛОГІКА ШІ (Gemini 1.5/2.0)
# ==========================================
async def ask_gemini(prompt: str):
    try:
        # Використовуємо 1.5-flash як найбільш стабільну для безкоштовних квот
        # Якщо хочете повернути 2.0, змініть назву моделі нижче
        response = client.models.generate_content(
            model='gemini-1.5-flash', 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        logging.error(f"AI Error: {e}")
        if "429" in str(e):
            return "⏳ Занадто багато запитів. Почекайте хвилину."
        if "403" in str(e):
            return "❌ Помилка доступу Google API (можливо, регіон)."
        return f"⚠️ Помилка ШІ: {str(e)[:50]}..."

# ==========================================
# 🤖 ХЕНДЛЕРИ ТЕЛЕГРАМ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Реєстрація користувача в БД
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", 
                    (message.from_user.id, message.from_user.username))
        conn.commit()
        cur.close()
        conn.close()
    except: pass

    await message.answer(
        f"🚀 <b>Привіт, {message.from_user.first_name}!</b>\n\n"
        "Я підключений до бази Neon та ШІ Gemini. Напиши мені будь-яке питання!",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_text(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    ai_response = await ask_gemini(message.text)
    await message.answer(ai_response)

# ==========================================
# 🚀 ГОЛОВНИЙ ЗАПУСК
# ==========================================
async def main():
    # Ініціалізація БД
    init_db()
    
    # Запуск веб-сервера
    await start_web_server()
    
    # Очистка черги повідомлень
    await bot.delete_webhook(drop_pending_updates=True)
    
    logging.info("🚀 Полінг запущено!")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот зупинений.")
