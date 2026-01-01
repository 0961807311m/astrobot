import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

# Отримуємо ключ із налаштувань Render (без проксі)
API_KEY = os.getenv("API_KEY")
MODEL_ID = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={API_KEY}"

# 1. ОБРОБНИК КОМАНДИ /START
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    # Створюємо кнопки головного меню
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="📅 Мої дні народження"), types.KeyboardButton(text="📝 Мої завдання")],
        [types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Оберіть дію..."
    )
    
    await message.answer(
        "👋 <b>Привіт! Я твій Астро-помічник.</b>\n\n"
        "Я допоможу тобі пам'ятати про важливі дати, керувати завданнями "
        "та даватиму астрологічні поради за допомогою ШІ Gemini.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# 2. ДІАГНОСТИКА (ОЧИЩЕНА ВІД ПРОКСІ)
@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 <b>Перевірка зв'язку з Gemini 2.0 (Render)...</b>", parse_mode="HTML")

    results = []
    # Прямий зв'язок без PROXY_URL
    async with aiohttp.ClientSession() as session:
        # Тест ШІ
        payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
        try:
            async with session.post(GEMINI_URL, json=payload, timeout=10) as ai_resp:
                if ai_resp.status == 200:
                    results.append(f"1. 🚀 <b>Сервер:</b> Render (Direct)")
                    results.append(f"2. 🤖 <b>Gemini API:</b> ✅ ГОТОВИЙ (200)")
                else:
                    results.append(f"1. 🤖 <b>Gemini API:</b> ❌ СТАТУС {ai_resp.status}")
        except Exception as e:
            results.append(f"1. 🤖 <b>Gemini API:</b> ❌ ПОМИЛКА: {str(e)[:30]}")

    await wait_msg.edit_text("\n".join(results), parse_mode="HTML")
