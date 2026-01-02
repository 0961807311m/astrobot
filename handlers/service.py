=import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

API_KEY = os.getenv("API_KEY")
# Тільки цей формат URL гарантовано працює без 404 на Render
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("✅ <b>Зв'язок встановлено!</b>\nОберіть дію:", reply_markup=keyboard, parse_mode="HTML")

@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 Перевірка моделі <b>gemini-1.5-flash</b>...")
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_URL, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    await wait_msg.edit_text("✅ <b>Gemini API: 200 OK</b>\nВсе працює ідеально!")
                elif resp.status == 404:
                    await wait_msg.edit_text("❌ 404: Модель не знайдена. Перевірте API_KEY або регіон.")
                else:
                    await wait_msg.edit_text(f"❓ Статус {resp.status}")
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ Помилка: {str(e)[:50]}")
