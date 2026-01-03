import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

# Отримуємо ключ
API_KEY = os.getenv("API_KEY", "").strip()

# ВИПРАВЛЕННЯ: Використовуємо модель зі списку доступних (Gemini 2.0 Flash)
# Це найшвидша модель, яка доступна у вашому проекті
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer(
        "🚀 <b>Астро-бот підключено до Gemini 2.0!</b>\n\nТепер я працюю на найновішій моделі від Google.", 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )

@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    if not API_KEY:
        await message.answer("❌ Помилка: API_KEY не знайдено.")
        return

    wait_msg = await message.answer("🔍 Запит до <b>Gemini 2.0 Flash</b>...")
    
    headers = {'Content-Type': 'application/json'}
    # Структура запиту для моделей 2.0 залишається такою ж
    payload = {"contents": [{"parts": [{"text": "Напиши 'Готово!'"}]}]}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_URL, json=payload, headers=headers) as resp:
                data = await resp.json()
                
                if resp.status == 200:
                    text_reply = data['candidates'][0]['content']['parts'][0]['text']
                    await wait_msg.edit_text(f"✅ <b>200 OK!</b>\nВідповідь ШІ: {text_reply}")
                else:
                    err_message = data.get("error", {}).get("message", "Невідома помилка")
                    await wait_msg.edit_text(f"❌ <b>Помилка {resp.status}</b>\n{err_message}")
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ Помилка з'єднання: {str(e)[:50]}")
