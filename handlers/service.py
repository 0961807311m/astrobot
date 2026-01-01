import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

# Отримуємо ключ із налаштувань Render (БЕЗ проксі)
API_KEY = os.getenv("API_KEY")
MODEL_ID = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={API_KEY}"

# 1. ОБРОБНИК КОМАНДИ /START
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    # Створюємо кнопки меню
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="📅 Мої дні народження"), types.KeyboardButton(text="🛠 Діагностика ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True
    )
    
    await message.answer(
        "👋 <b>Привіт! Я твій Астро-помічник на Render.</b>\n\n"
        "Оберіть дію на клавіатурі нижче:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# 2. ДІАГНОСТИКА (БЕЗ ПРОКСІ)
@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 <b>Перевірка зв'язку...</b>", parse_mode="HTML")
    async with aiohttp.ClientSession() as session:
        try:
            payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
            async with session.post(GEMINI_URL, json=payload, timeout=10) as ai_resp:
                status = "✅ ГОТОВИЙ" if ai_resp.status == 200 else f"❌ ПОМИЛКА {ai_resp.status}"
                await wait_msg.edit_text(f"🤖 <b>Gemini API:</b> {status}", parse_mode="HTML")
        except Exception as e:
            await wait_msg.edit_text(f"❌ <b>Помилка:</b> {str(e)[:30]}", parse_mode="HTML")
