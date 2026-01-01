import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import web
import database as db
from handlers import service, birthdays, ai_advice, shift  # Переконайтеся, що всі файли є в папці handlers

TOKEN = os.getenv("BOT_TOKEN")

# 1. Обробка запиту для Render (щоб сервіс був Live)
async def handle(request):
    return web.Response(text="Bot is alive!")

# 2. Запуск веб-сервера (Health Check)
async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Порт 10000 — стандарт для Render
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ Веб-сервер запущено на порту {port}")

async def main():
    # 3. Ініціалізація бази даних Neon
    try:
        db.init_db()
        print("✅ База даних Neon підключена успішно")
    except Exception as e:
        print(f"❌ Помилка бази даних: {e}")

    # 4. Запускаємо веб-сервер
    await run_web_server()

    # 5. Ініціалізація бота
    # Використовуємо AiohttpSession для стабільної роботи на серверах
    bot = Bot(token=TOKEN, session=AiohttpSession())
    dp = Dispatcher()

    # 6. Реєстрація роутерів (Важливо: service перший!)
    dp.include_router(service.router)      # Обробка /start та головного меню
    dp.include_router(birthdays.router)    # Логіка днів народження
    dp.include_router(ai_advice.router)    # Поради ШІ
    dp.include_router(shift.router)        # Завдання та черги

    print("🚀 Бот запускається у режимі Polling...")
    
    # Очищуємо чергу повідомлень, які прийшли, поки бот був офлайн
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запуск прослуховування
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот зупинений")
