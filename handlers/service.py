import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

# Отримуємо ключ та перевіряємо його наявність
API_KEY = os.getenv("API_KEY", "").strip()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("✅ **Бот працює!** Оберіть дію:", reply_markup=keyboard, parse_mode="HTML")

@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    if not API_KEY:
        await message.answer("❌ API_KEY не знайдено в налаштуваннях Render!")
        return

    wait_msg = await message.answer("🔍 Запит до Google Gemini API...")
    
    # Спробуємо максимально універсальний шлях v1beta
    # Якщо 1.5-flash не працює, пробуємо gemini-pro
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": "Say OK"}]}]}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    await wait_msg.edit_text("✅ **200 OK**: Gemini Pro працює!")
                else:
                    data = await resp.json()
                    err_msg = data.get("error", {}).get("message", "Unknown error")
                    await wait_msg.edit_text(f"❌ **Помилка {resp.status}**\nДеталі: {err_msg}")
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ Помилка з'єднання: {str(e)[:50]}")
