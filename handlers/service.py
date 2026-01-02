import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

# 1. Ініціалізація роутера
router = Router()

# 2. Налаштування Gemini
API_KEY = os.getenv("API_KEY")
MODEL_ID = "gemini-2.0-flash"
# Використовуємо стабільну версію v1
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_ID}:generateContent?key={API_KEY}"

# 3. Обробник команди /start
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True
    )
    
    await message.answer(
        "👋 <b>Привіт! Я твій Астро-помічник на Render.</b>\n\n"
        "Оберіть дію на клавіатурі нижче:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# 4. Діагностика ШІ
@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 <b>Перевірка зв'язку з Google AI...</b>", parse_mode="HTML")
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_URL, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    await wait_msg.edit_text("✅ <b>Gemini API: 200 OK</b>\nЗв'язок працює ідеально!", parse_mode="HTML")
                elif resp.status == 403:
                    await wait_msg.edit_text("❌ <b>Помилка 403</b>\nGoogle відхиляє ключ. Переконайтеся, що ви змінили регіон на Frankfurt.")
                else:
                    raw_res = await resp.text()
                    await wait_msg.edit_text(f"❓ <b>Статус: {resp.status}</b>\n{raw_res[:50]}")
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ <b>Помилка з'єднання:</b>\n{str(e)[:50]}")
