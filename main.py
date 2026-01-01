import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import web
import database as db
from handlers import service, birthdays, ai_advice, shift

TOKEN = os.getenv("BOT_TOKEN")

async def handle(request):
    return web.Response(text="Bot is alive!")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ Веб-сервер запущено на порту {port}")

async def main():
    try:
        db.init_db()
        print("✅ База даних Neon підключена успішно")
    except Exception as e:
        print(f"❌ Помилка бази даних: {e}")

    await run_web_server()

    bot = Bot(token=TOKEN, session=AiohttpSession())
    dp = Dispatcher()

    # Порядок реєстрації: service завжди перший!
    dp.include_router(service.router)
    dp.include_router(birthdays.router)
    dp.include_router(ai_advice.router)
    dp.include_router(shift.router)

    print("🚀 Бот запускається у режимі Polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
