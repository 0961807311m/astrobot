import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

API_KEY = os.getenv("API_KEY")
# Використовуємо пряму назву моделі без зайвих змінних, щоб уникнути 404
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("👋 <b>Бот активований!</b>\nОберіть дію на клавіатурі:", reply_markup=keyboard, parse_mode="HTML")

@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 Перевірка моделі <b>gemini-1.5-flash</b>...", parse_mode="HTML")
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_URL, json=payload, headers=headers, timeout=10) as resp:
                data = await resp.json()
                if resp.status == 200:
                    await wait_msg.edit_text("✅ <b>200 OK:</b> Модель знайдена і працює!")
                elif resp.status == 404:
                    await wait_msg.edit_text("❌ <b>Помилка 404:</b> Google не бачить модель. Спробуйте змінити регіон на Frankfurt.")
                else:
                    msg = data.get("error", {}).get("message", "Unknown error")
                    await wait_msg.edit_text(f"❓ <b>Статус {resp.status}:</b> {msg[:100]}")
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ Помилка мережі: {str(e)[:50]}")
