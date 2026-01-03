import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from google import genai
from google.genai import types as genai_types

# ==========================================
# ⚙️ КОНФІГУРАЦІЯ
# ==========================================
# Отримуємо токени зі змінних середовища Render
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("API_KEY")

# Ініціалізація клієнтів
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = genai.Client(api_key=GEMINI_KEY)

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# ==========================================
# 🧠 ЛОГІКА ШІ (Gemini 2.0 Flash)
# ==========================================
async def ask_gemini(prompt: str):
    try:
        # Використовуємо модель 2.0 Flash, як у твоєму прикладі
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        logging.error(f"Помилка ШІ: {e}")
        # Якщо 429 (ліміти) або 404, бот скаже про це
        if "429" in str(e):
            return "⚠️ Помилка: Перевищено ліміт запитів Google. Спробуйте через хвилину."
        return f"❌ Помилка ШІ: {str(e)[:100]}"

# ==========================================
# 🤖 ОБРОБНИКИ ТЕЛЕГРАМ
# ==========================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🚀 <b>Бот активований!</b>\n"
        "Я працюю на базі Gemini 2.0 Flash. Напиши мені щось!",
        parse_mode="HTML"
    )

@dp.message(F.text)
async def handle_text(message: types.Message):
    # Показуємо статус "друкує", щоб користувач знав, що ШІ думає
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    user_text = message.text
    ai_response = await ask_gemini(user_text)
    
    await message.answer(ai_response)

# ==========================================
# 🚀 ЗАПУСК
# ==========================================
async def main():
    logging.info("🚀 Бот запускається у режимі Polling...")
    # Видаляємо вебхуки, якщо вони були раніше (це фіксить Conflict)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот зупинений.")
