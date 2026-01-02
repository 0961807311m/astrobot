import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

# 1. Створення роутера
router = Router()

# 2. Налаштування Gemini (v1beta + прямий шлях до моделі)
API_KEY = os.getenv("API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"

# 3. Стартове повідомлення та клавіатура
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Оберіть пункт меню..."
    )
    
    await message.answer(
        "👋 <b>Привіт! Я твій Астро-помічник.</b>\n\n"
        "Я можу давати астрологічні поради за допомогою ШІ та зберігати дні народження друзів.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# 4. Функція діагностики ШІ
@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 <b>З'єднуюсь із Google Gemini API...</b>", parse_mode="HTML")
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{"text": "Напиши 'OK', якщо все працює."}]
        }]
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(GEMINI_URL, json=payload, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    await wait_msg.edit_text(
                        "✅ <b>Gemini API: 200 OK</b>\n\nМодель знайдена і готова до роботи!",
                        parse_mode="HTML"
                    )
                elif resp.status == 404:
                    await wait_msg.edit_text(
                        "❌ <b>Помилка 404 (Not Found)</b>\n\nGoogle не бачить модель. Перевірте правильність написання URL або API ключа.",
                        parse_mode="HTML"
                    )
                elif resp.status == 403:
                    await wait_msg.edit_text(
                        "❌ <b>Помилка 403 (Forbidden)</b>\n\nДоступ заблоковано. Переконайтеся, що регіон на Render — <b>Frankfurt</b>.",
                        parse_mode="HTML"
                    )
                else:
                    error_text = await resp.text()
                    await wait_msg.edit_text(
                        f"❓ <b>Статус: {resp.status}</b>\n\n{error_text[:100]}...",
                        parse_mode="HTML"
                    )
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ <b>Помилка мережі:</b>\n<code>{str(e)[:100]}</code>", parse_mode="HTML")
