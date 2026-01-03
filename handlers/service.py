import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

API_KEY = os.getenv("API_KEY", "").strip()

# Спробуємо альтернативний URL, який іноді допомагає уникнути 404
# Ми використовуємо модель gemini-1.0-pro - вона найстаріша і має бути у всіх
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={API_KEY}"

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("🚀 <b>Бот готовий до останньої спроби діагностики!</b>", reply_markup=keyboard, parse_mode="HTML")

@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    if not API_KEY:
        await message.answer("❌ API_KEY порожній!")
        return

    wait_msg = await message.answer("🔍 Пробую модель <b>gemini-pro</b> (v1beta)...")
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_URL, json=payload, headers=headers) as resp:
                data = await resp.json()
                
                if resp.status == 200:
                    await wait_msg.edit_text("✅ <b>Успіх! 200 OK</b>\nМодель gemini-pro працює. Можемо використовувати її.")
                else:
                    # Якщо знову 404, спробуємо вивести список доступних моделей прямо в чат!
                    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
                    async with session.get(list_url) as list_resp:
                        models_data = await list_resp.json()
                        available_models = [m.get("name") for m in models_data.get("models", [])[:5]]
                        models_str = "\n".join(available_models) if available_models else "Список порожній"
                        
                        error_msg = data.get("error", {}).get("message", "Unknown error")
                        await wait_msg.edit_text(
                            f"❌ <b>Помилка {resp.status}</b>\n{error_msg}\n\n"
                            f"📋 <b>Доступні тобі моделі:</b>\n<code>{models_str}</code>",
                            parse_mode="HTML"
                        )
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ Помилка: {str(e)[:50]}")
