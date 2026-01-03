import os
import asyncio
import logging
import psycopg2
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
import google.generativeai as genai

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

# Ініціалізація Google AI Studio
genai.configure(api_key=GEMINI_KEY)

bot = Bot(token=TOKEN)
dp = Dispatcher()

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
        logging.info("✅ База даних підключена успішно")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# ==========================================
# 🧠 РОБОТА З ШІ (СИСТЕМА ПЕРЕБОРУ МОДЕЛЕЙ)
# ==========================================
async def ask_gemini(prompt: str):
    # Список назв моделей, які Google може вимагати залежно від регіону/проекту
    models_to_try = [
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-pro'
    ]
    
    last_error = ""
    
    for model_name in models_to_try:
        try:
            logging.info(f"🤖 Спроба отримати відповідь від: {model_name}")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            
            if response and response.text:
                logging.info(f"✅ Успіх з моделлю: {model_name}")
                return response.text.strip()
                
        except Exception as e:
            last_error = str(e)
            logging.warning(f"⚠️ Модель {model_name} видала помилку: {last_error[:100]}")
            continue # Переходимо до наступної моделі в списку

    # Якщо всі моделі зі списку видали помилку
    if "429" in last_error:
        return "⏳ Ліміт запитів вичерпано. Спробуйте через 1-2 хвилини."
    if "404" in last_error:
        return "❌ Помилка 404: Моделі не знайдені. Спробуйте оновити API ключ у Google AI Studio."
    
    return "⚠️ ШІ тимчасово не відповідає. Спробуйте пізніше."

# ==========================================
# 🤖 ОБРОБНИКИ ТЕЛЕГРАМ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Реєстрація користувача
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
        f"🚀 <b>Вітаю, {message.from_user.first_name}!</b>\n\n"
        "Я активний і готовий до роботи. Напиши мені будь-яке запитання!",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_text(message: types.Message):
    # Анімація "друкує..."
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    ai_response = await ask_gemini(message.text)
    await message.answer(ai_response)

# ==========================================
# 🌐 ВЕБ-СЕРВЕР ТА ЗАПУСК
# ==========================================
async def handle_ping(request):
    return web.Response(text="Bot is alive")

async def main():
    # 1. БД
    init_db()
    
    # 2. Веб-сервер для Render (порт 10000)
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    
    # 3. Очищення старих запитів та запуск
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🚀 Бот запущений!")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот зупинений.")
