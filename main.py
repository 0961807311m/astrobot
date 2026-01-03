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
# 🌐 ВЕБ-СЕРВЕР (Для Render/UptimeRobot)
# ==========================================
async def handle_ping(request):
    return web.Response(text="Bot is Online!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logging.info("✅ Веб-сервер запущено на порту 10000")

# ==========================================
# 🧠 РОБОТА З ШІ (Cascade Model System)
# ==========================================
async def ask_gemini(prompt: str):
    # Список моделей за пріоритетом: 2.0 -> 1.5 Latest -> 1.5 Stable
    models_to_try = ['gemini-2.0-flash-exp', 'gemini-1.5-flash-latest', 'gemini-1.5-flash']
    last_error = ""

    for model_name in models_to_try:
        try:
            logging.info(f"🤖 Спроба запиту до: {model_name}")
            response = client.models.generate_content(
                model=model_name, 
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            last_error = str(e)
            logging.warning(f"⚠️ {model_name} недоступна: {last_error[:50]}")
            continue # Пробуємо наступну модель

    # Якщо жодна не спрацювала
    if "429" in last_error:
        return "⏳ Всі версії ШІ зараз перевантажені. Спробуйте через хвилину."
    return "⚠️ ШІ тимчасово недоступний. Пробуємо відновити зв'язок."

# ==========================================
# 🤖 ОБРОБНИКИ ТЕЛЕГРАМ
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
    except: pass

    await message.answer(
        f"🚀 <b>Привіт, {message.from_user.first_name}!</b>\n\n"
        "Я працюю на базі Gemini 2.0 та 1.5 Flash. Запитуй що завгодно!",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_text(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    ai_response = await ask_gemini(message.text)
    await message.answer(ai_response)

# ==========================================
# 🚀 ЗАПУСК
# ==========================================
async def main():
    init_db()
    await start_web_server()
    # Видаляємо вебхук для уникнення конфліктів при передеплої
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
