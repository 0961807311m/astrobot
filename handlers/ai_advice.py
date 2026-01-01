import aiohttp
import asyncio
import json
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database as db

router = Router()

# ВИКОРИСТОВУЙТЕ ВАШ НОВИЙ КЛЮЧ
API_KEY = "ВАШ_НОВИЙ_КЛЮЧ"
MODEL_ID = "gemini-1.5-flash"
# Стабільне посилання v1
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_ID}:generateContent?key={API_KEY}"
PROXY_URL = "http://proxy.server:3128"

class AstroStates(StatesGroup):
    waiting_for_data = State()

async def get_gemini_response(prompt):
    """Функція з 3 спробами подолати помилку 429"""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": 200}
    }
    headers = {'Content-Type': 'application/json'}

    async with aiohttp.ClientSession() as session:
        for attempt in range(3):  # Робимо до 3 спроб
            try:
                async with session.post(GEMINI_URL, json=payload, headers=headers, proxy=PROXY_URL, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data['candidates'][0]['content']['parts'][0]['text'], None

                    elif resp.status == 429:
                        # Якщо 429, чекаємо 10 секунд і пробуємо знову
                        if attempt < 2:
                            await asyncio.sleep(10)
                            continue
                        return None, "LIMIT_429"

                    else:
                        error_text = await resp.text()
                        return None, f"Status {resp.status}"
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(5)
                    continue
                return None, f"Error: {str(e)[:15]}"
    return None, "TIMEOUT"

@router.message(F.text == "✨ Порада дня")
async def get_ai_advice(message: types.Message, state: FSMContext):
    user_info = db.get_astro_data(message.from_user.id)

    if not user_info:
        await message.answer("🔮 Спочатку введіть дату народження (напр. 10.10.1990):")
        await state.set_state(AstroStates.waiting_for_data)
        return

    wait_msg = await message.answer("📡 <i>З'єднуюсь з сервером Gemini... (спроба 1/3)</i>", parse_mode="HTML")

    prompt = f"Ти професійний астролог. На основі даних: {user_info}, напиши коротку пораду на сьогодні (2 речення)."

    # Викликаємо функцію, яка сама буде робити повтори при 429
    response_text, error_info = await get_gemini_response(prompt)

    if response_text:
        await wait_msg.edit_text(f"✨ <b>ВАША ПОРАДА:</b>\n\n{response_text}", parse_mode="HTML")
    elif error_info == "LIMIT_429":
        await wait_msg.edit_text("⏳ <b>Сервер Google перевантажений.</b>\n\nНавіть після 3 спроб відповідь не отримана. Будь ласка, спробуйте через 5-10 хвилин.")
    else:
        await wait_msg.edit_text(f"🛰 <b>Технічна помилка:</b> {error_info}")

@router.message(AstroStates.waiting_for_data)
async def process_astro_data(message: types.Message, state: FSMContext):
    db.save_astro_data(message.from_user.id, message.text)
    await message.answer("✅ Дані збережено! Тисніть ✨ <b>Порада дня</b>")
    await state.clear()
