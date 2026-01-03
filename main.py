import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web  # Додано для веб-сервера
from google import genai

# Налаштування
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_KEY)

logging.basicConfig(level=logging.INFO)

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER (Keep-alive) ---
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render автоматично шукає порт 10000
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logging.info("✅ Веб-сервер запущено на порту 10000")

# --- ЛОГІКА ШІ ---
async def ask_gemini(prompt: str):
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        return f"❌ Помилка ШІ: {str(e)[:100]}"

# --- ХЕНДЛЕРИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("🚀 Бот онлайн! Напиши мені щось.")

@dp.message(F.text)
async def handle_text(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    ai_response = await ask_gemini(message.text)
    await message.answer(ai_response)

# --- ЗАПУСК ---
async def main():
    # 1. Запускаємо веб-сервер
    await start_web_server()
    
    # 2. Очищуємо старі підключення (вирішує ConflictError)
    await bot.delete_webhook(drop_pending_updates=True)
    
    logging.info("🚀 Полінг запущено!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот зупинений.")
