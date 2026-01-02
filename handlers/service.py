import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

# 1. Ініціалізація роутера
router = Router()

# 2. Налаштування Gemini
# Використовуємо v1beta, оскільки вона стабільніше працює з flash-моделями
API_KEY = os.getenv("API_KEY")
MODEL_ID = "gemini-1.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={API_KEY}"

# 3. Стартова команда
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb, 
        resize_keyboard=True,
        input_field_placeholder="Оберіть дію..."
    )
    
    await message.answer(
        "👋 <b>Привіт! Я твій Астро-помічник.</b>\n\n"
        "Я можу зберігати дні народження та давати поради за допомогою ШІ.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# 4. Діагностика ШІ (з виправленням 404/403)
@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 <b>Перевірка зв'язку з Gemini API...</b>", parse_mode="HTML")
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": "Write 'Success'"}]
        }]
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_URL, json=payload, headers=headers, timeout=15) as resp:
                data = await resp.json()
                
                if resp.status == 200:
                    await wait_msg.edit_text(
                        "✅ <b>Gemini API: 200 OK</b>\nМодель знайдена та працює успішно!",
                        parse_mode="HTML"
                    )
                elif resp.status == 404:
                    await wait_msg.edit_text(
                        "❌ <b>Помилка 404</b>\nGoogle не бачить модель. Перевірте, чи правильно вказано API_KEY у налаштуваннях Render.",
                        parse_mode="HTML"
                    )
                elif resp.status == 403:
                    error_detail = data.get("error", {}).get("message", "")
                    await wait_msg.edit_text(
                        f"❌ <b>Помилка 403 (Forbidden)</b>\n\nДеталі: {error_detail}\n\n"
                        "<b>Рішення:</b> Перевірте, щоб регіон на Render був <b>Frankfurt</b>.",
                        parse_mode="HTML"
                    )
                else:
                    msg = data.get("error", {}).get("message", "Невідома помилка")
                    await wait_msg.edit_text(f"❓ <b>Статус {resp.status}:</b>\n{msg}")
                    
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ <b>Помилка мережі:</b>\n<code>{str(e)[:100]}</code>", parse_mode="HTML")
