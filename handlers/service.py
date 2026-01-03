import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

# Отримуємо ключ
API_KEY = os.getenv("API_KEY", "").strip()

# ФІКС 404: Переходимо на стабільну версію v1 та використовуємо перевірену назву моделі
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer(
        "👋 <b>Астро-бот готовий!</b>\nВикористовуйте меню для навігації:", 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )

@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    if not API_KEY:
        await message.answer("❌ Помилка: API_KEY порожній у налаштуваннях Render.")
        return

    wait_msg = await message.answer("🔍 Запит до <b>Gemini 1.5 Flash (v1)</b>...")
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": "Say 'OK'"}]}]}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_URL, json=payload, headers=headers) as resp:
                data = await resp.json()
                
                if resp.status == 200:
                    await wait_msg.edit_text("✅ <b>200 OK</b>: Модель знайдена і відповідає!")
                else:
                    # Отримуємо детальне повідомлення про помилку
                    err_message = data.get("error", {}).get("message", "Unknown error")
                    await wait_msg.edit_text(f"❌ <b>Помилка {resp.status}</b>\n{err_message}")
                    
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ Помилка з'єднання: {str(e)[:50]}")
