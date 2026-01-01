import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import web
import database as db
from handlers import birthdays, ai_advice, shift, service

TOKEN = os.getenv("BOT_TOKEN")

# 1. Функція обробки запиту від Render
async def handle(request):
    return web.Response(text="Bot is alive!")

# 2. Функція запуску веб-сервера
async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render автоматично надає порт у змінну PORT
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ Веб-сервер запущено на порту {port}")

async def main():
    # 3. Ініціалізація бази (Neon)
    try:
        db.init_db()
        print("✅ База даних Neon підключена")
    except Exception as e:
        print(f"❌ Помилка бази даних: {e}")

    # 4. ЗАПУСКАЄМО ВЕБ-СЕРВЕР ПЕРШИМ
    await run_web_server()

    # 5. Ініціалізація бота
    bot = Bot(token=TOKEN, session=AiohttpSession())
    dp = Dispatcher()

    # Реєстрація роутерів
    dp.include_router(birthdays.router)
    dp.include_router(ai_advice.router)
    dp.include_router(shift.router)
    dp.include_router(service.router)

    print("🚀 Бот запускається у режимі Polling...")
    
    # Очищуємо старі повідомлення та запускаємо
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
