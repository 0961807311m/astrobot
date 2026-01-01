import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
import database as db
from handlers import birthdays, ai_advice, shift, service

# Отримуємо токен із налаштувань Render
TOKEN = os.getenv("BOT_TOKEN")

async def main():
    # Ініціалізація бази даних Neon
    try:
        db.init_db()
        print("✅ База даних Neon підключена успішно")
    except Exception as e:
        print(f"❌ Помилка бази даних: {e}")

    # Створюємо бота БЕЗ проксі
    bot = Bot(token=TOKEN, session=AiohttpSession())
    dp = Dispatcher()

    # Реєстрація всіх роутерів
    dp.include_router(birthdays.router)
    dp.include_router(ai_advice.router)
    dp.include_router(shift.router)
    dp.include_router(service.router)

    print("🚀 Бот запущений на Render!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
