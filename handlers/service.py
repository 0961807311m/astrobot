import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

API_KEY = os.getenv("API_KEY")
MODEL_ID = "gemini-1.5-flash"  # Найстабільніша модель
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_ID}:generateContent?key={API_KEY}"

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
    wait_msg = await message.answer("🔍 Перевірка зв'язку...")
    async with aiohttp.ClientSession() as session:
        try:
            payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
            headers = {'Content-Type': 'application/json'}
            async with session.post(GEMINI_URL, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    await wait_msg.edit_text("✅ <b>Gemini API: 200 OK</b>")
                else:
                    await wait_msg.edit_text(f"❌ <b>Помилка {resp.status}</b>\nПеревірте Регіон на Frankfurt.")
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ Помилка: {str(e)[:40]}")
