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
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Ініціалізація клієнтів
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
        # Створення таблиці користувачів, якщо її немає
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
# 🌐 ВЕБ-СЕРВЕР (Для запобігання сплячці Render)
# ==========================================
async def handle_ping(request):
    return web.Response(text="WorkDays Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render використовує порт 10000 для HTTP-трафіку
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logging.info("✅ Веб-сервер запущено на порту 10000")

# ==========================================
# 🧠 ЛОГІКА ШІ (Gemini 1.5 Flash)
# ==========================================
async def ask_gemini(prompt: str):
    try:
        # Використовуємо 1.5-flash через проблеми з квотами у версії 2.0
        response = client.models.generate_content(
            model='gemini-1.5-flash', 
            contents=prompt
        )
        if response and response.text:
            return response.text.strip()
        return "🤖 ШІ не зміг сформувати відповідь."
    except Exception as e:
        logging.error(f"AI Error: {e}")
        if "429" in str(e):
            return "⏳ Ліміт запитів вичерпано. Почекайте хвилину."
        if "403" in str(e):
            return "❌ Помилка доступу. Можливо, ваш API-ключ заблоковано або невірний регіон."
        return f"⚠️ ШІ тимчасово недоступний."

# ==========================================
# 🤖 ОБРОБНИКИ ПОВІДОМЛЕНЬ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Логіка збереження користувача в БД Neon
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (message.from_user.id, message.from_user.username)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"DB Insert Error: {e}")

    await message.answer(
        f"🚀 <b>Привіт, {message.from_user.first_name}!</b>\n\n"
        "Я бот, підключений до бази Neon та ШІ Gemini. Запитуй що завгодно!",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_text(message: types.Message):
    # Показуємо статус "друкує"
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    ai_response = await ask_gemini(message.text)
    await message.answer(ai_response)

# ==========================================
# 🚀 ГОЛОВНИЙ ЗАПУСК
# ==========================================
async def main():
    # 1. Ініціалізація бази даних
    init_db()
    
    # 2. Запуск веб-сервера для Render
    await start_web_server()
    
    # 3. Видалення вебхука для Polling
    await bot.delete_webhook(drop_pending_updates=True)
    
    logging.info("🚀 Бот запускається у режимі Polling...")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот зупинений.")
