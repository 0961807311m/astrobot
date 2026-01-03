import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
from google import genai

# ==========================================
# ⚙️ НАЛАШТУВАННЯ ТА ЛОГУВАННЯ
# ==========================================
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Ініціалізація
bot = Bot(token=TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_KEY)

# ==========================================
# 🗄️ РОБОТА З БАЗОЮ ДАНИХ NEON
# ==========================================
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
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
        logging.info("✅ База даних Neon підключена")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# ==========================================
# 🌐 ВЕБ-СЕРВЕР (Для Uptime Monitor)
# ==========================================
async def handle_ping(request):
    return web.Response(text="WorkDays Bot Status: OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render автоматично шукає порт 10000
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logging.info("✅ Веб-сервер активний на порту 10000")

# ==========================================
# 🧠 ВЗАЄМОДІЯ З GEMINI ШІ
# ==========================================
async def ask_gemini(prompt: str):
    try:
        # ВАЖЛИВО: для нової бібліотеки використовуємо просто 'gemini-1.5-flash'
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
            return "⏳ Ліміт запитів вичерпано. Спробуйте через хвилину."
        return "⚠️ ШІ тимчасово не відповідає."

# ==========================================
# 🤖 ОБРОБКА ПОВІДОМЛЕНЬ ТЕЛЕГРАМ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
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
    except:
        pass

    await message.answer(
        f"🚀 <b>Привіт, {message.from_user.first_name}!</b>\n\n"
        "Я твій ШІ-помічник. Запитуй що завгодно!",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_text(message: types.Message):
    # Ефект "друкує..."
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    ai_response = await ask_gemini(message.text)
    await message.answer(ai_response)

# ==========================================
# 🚀 ЗАПУСК ТА ЗАВЕРШЕННЯ
# ==========================================
async def main():
    # 1. Підготовка БД
    init_db()
    
    # 2. Запуск веб-сервера (щоб Render не "спав")
    await start_web_server()
    
    # 3. Видалення вебхука (критично для Polling)
    await bot.delete_webhook(drop_pending_updates=True)
    
    logging.info("🚀 Бот запущений!")
    
    try:
        await dp.start_polling(bot)
    finally:
        # Коректне закриття з'єднань
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот вимкнений.")
