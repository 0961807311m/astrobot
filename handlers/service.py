import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

# Отримуємо ключ
API_KEY = os.getenv("API_KEY")

# ФІКС 404: Пряме посилання без зайвих змінних у самому URL
# Використовуємо v1beta/models/gemini-1.5-flash:generateContent
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer(
        "👋 <b>Бот онлайн!</b>\nВикористовуйте кнопки нижче:", 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )

@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 Запит до Google Gemini v1beta...")
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": "Say OK"}]}]}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_URL, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    await wait_msg.edit_text("✅ <b>200 OK</b>: ШІ працює!")
                elif resp.status == 404:
                    await wait_msg.edit_text(
                        "❌ <b>Помилка 404</b>\nМодель не знайдена. Перевірте, чи не видалили ви випадково символи з API_KEY в Render."
                    )
                elif resp.status == 403:
                    await wait_msg.edit_text(
                        "❌ <b>Помилка 403</b>\nДоступ обмежено. Перевірте, що регіон сервісу — <b>Frankfurt</b>."
                    )
                else:
                    data = await resp.text()
                    await wait_msg.edit_text(f"❓ <b>Помилка {resp.status}</b>\n{data[:100]}")
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ Помилка: {str(e)[:50]}")
