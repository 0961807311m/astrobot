import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

# 1. СПОЧАТКУ СТВОРЮЄМО РОУТЕР
router = Router()

# 2. ПОТІМ НАЛАШТУВАННЯ
API_KEY = os.getenv("API_KEY")
MODEL_ID = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_ID}:generateContent?key={API_KEY}"

# 3. ПОТІМ ОБРОБНИКИ (декоратори @router...)
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("👋 <b>Привіт! Я твій Астро-помічник.</b>", reply_markup=keyboard, parse_mode="HTML")

@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    # ... весь інший код діагностики ...
