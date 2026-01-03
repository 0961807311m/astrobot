import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiohttp import web
from google import genai

# Налаштування логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_KEY)

# Веб-сервер для Render
async def handle_ping(request):
    return web.Response(text="WorkdaysMHP_bot is alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logging.info("✅ Веб-сервер на порту 10000 запущено")

# ШІ логіка
async def ask_gemini(prompt: str):
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp', contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return "⚠️ ШІ тимчасово недоступний."

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(f"👋 Вітаю! Я бот @WorkdaysMHP_bot. Напиши мені!")

@dp.message(F.text)
async def handle_text(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    res = await ask_gemini(message.text)
    await message.answer(res)

async def main():
    await start_web_server()
    # ВИДАЛЯЄМО ВСІ СТАРІ ЗАПИТИ, щоб зняти блокування Conflict/Unauthorized
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🚀 Полінг запускається...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
