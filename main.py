import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
from google import genai

# ==========================================
# ⚙️ НАЛАШТУВАННЯ
# ==========================================
# Отримання токенів з Environment Variables на Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("API_KEY")

# Налаштування логування для відстеження помилок у консолі Render
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Ініціалізація клієнтів (якщо токени відсутні, бот видасть помилку при запуску)
if not BOT_TOKEN:
    logging.error("❌ Змінна BOT_TOKEN не знайдена!")
if not GEMINI_KEY:
    logging.error("❌ Змінна API_KEY (для Gemini) не знайдена!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_KEY)

# ==========================================
# 🌐 ВЕБ-СЕРВЕР ДЛЯ KEEP-ALIVE (Порт 10000)
# ==========================================
async def handle_ping(request):
    """Відповідає 'OK' для моніторингу працездатності"""
    return web.Response(text="Bot is running and healthy!")

async def start_web_server():
    """Запускає сервер, щоб Render не вимикав бота"""
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render шукає порт 10000 за замовчуванням
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logging.info("✅ Веб-сервер запущено на порту 10000")

# ==========================================
# 🧠 ЛОГІКА ШІ (Gemini 2.0 Flash)
# ==========================================
async def ask_gemini(prompt: str):
    try:
        # Використовуємо експериментальну модель 2.0-flash-exp (вона найстабільніша для free tier)
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp', 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        error_str = str(e)
        logging.error(f"Помилка Gemini: {error_str}")
        if "429" in error_str:
            return "⚠️ Помилка: Перевищено ліміт запитів. Спробуйте через 60 секунд."
        return f"❌ Помилка ШІ: Не вдалося отримати відповідь."

# ==========================================
# 🤖 ОБРОБНИКИ ПОВІДОМЛЕНЬ
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 <b>Привіт! Я твій Астро-помічник.</b>\n\n"
        "Я використовую Gemini 2.0 для відповідей на твої питання. "
        "Просто напиши мені повідомлення!",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_text(message: types.Message):
    # Візуальний ефект "Бот пише..."
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    ai_response = await ask_gemini(message.text)
    await message.answer(ai_response)

# ==========================================
# 🚀 ЗАПУСК БОТА
# ==========================================
async def main():
    try:
        # 1. Запуск веб-сервера для Render
        await start_web_server()
        
        # 2. Видалення вебхука для усунення ConflictError
        logging.info("Перевірка авторизації...")
        await bot.delete_webhook(drop_pending_updates=True)
        
        logging.info("🚀 Бот успішно запущений у режимі Polling!")
        
        # 3. Старт прослуховування повідомлень
        await dp.start_polling(bot)
        
    except Exception as e:
        logging.error(f"❌ Критична помилка: {e}")
    finally:
        # Коректне закриття сесії, щоб не було 'Unclosed client session'
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот зупинений.")
