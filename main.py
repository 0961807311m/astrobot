import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

# Імпортуємо всі модулі
try:
    # Додаємо service у список імпортів для діагностики
    from handlers import birthdays, shift, ai_advice, shift_tasks, service
    import database as db
except ImportError as e:
    print(f"❌ Помилка імпорту: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)

# Твій токен
TOKEN = "8201600405:AAE8upEFnjzz8oBrQJxWYrMyoXyGA7gYGCQ"

async def main():
    # Ініціалізація бази даних (створення таблиць, якщо їх немає)
    db.init_db()

    # Налаштування проксі для PythonAnywhere (Free Tier)
    session = AiohttpSession(proxy="http://proxy.server:3128")
    bot = Bot(token=TOKEN, session=session)
    dp = Dispatcher()

    # Підключаємо всі роутери
    dp.include_router(birthdays.router)
    dp.include_router(shift.router)
    dp.include_router(ai_advice.router)
    dp.include_router(shift_tasks.router)
    dp.include_router(service.router) # Роутер для діагностики ШІ

    @dp.message(Command("start"))
    @dp.message(F.text.in_({"🔙 Головне меню", "Головне меню"}))
    async def cmd_start(message: types.Message):
        # Клавіатура з 5-ма кнопками
        kb = [
            [types.KeyboardButton(text="🚀 Початок зміни")],
            [types.KeyboardButton(text="🎂 Дні народження")],
            [types.KeyboardButton(text="✨ Порада дня"), types.KeyboardButton(text="📝 Завдання на зміну")],
            [types.KeyboardButton(text="🛠 Діагностика ШІ")] # Нова кнопка для перевірки
        ]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

        welcome_text = (
            f"👋 <b>Привіт, {message.from_user.first_name}!</b>\n\n"
            "Твій персональний асистент готовий до роботи.\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "✨ <b>Порада дня</b> — прогноз від Gemini\n"
            "📝 <b>Завдання на зміну</b> — голосовий список справ\n"
            "🛠 <b>Діагностика ШІ</b> — перевірка зв'язку з Google"
        )
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    print("🚀 Бот успішно запущений! Кнопка діагностики доступна.")

    # Очищуємо чергу оновлень та запускаємо бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот зупинений")
