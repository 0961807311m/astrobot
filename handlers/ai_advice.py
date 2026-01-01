import os
import aiohttp
from aiogram import Router, F, types
import database as db

router = Router()

API_KEY = os.getenv("API_KEY")
MODEL_ID = "gemini-1.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1/models/{MODEL_ID}:generateContent?key={API_KEY}"

@router.message(F.text == "✨ Порада дня")
async def get_ai_advice(message: types.Message):
    user_info = db.get_astro_data(message.from_user.id)
    
    if not user_info:
        await message.answer("🔮 Спочатку введіть дату народження у налаштуваннях.")
        return

    wait_msg = await message.answer("📡 <i>З'єднуюсь із Gemini...</i>", parse_mode="HTML")
    
    payload = {
        "contents": [{"parts": [{"text": f"Ти астролог. Дані: {user_info}. Дай коротку пораду на сьогодні."}]}]
    }

    async with aiohttp.ClientSession() as session:
        # Прямий запит без проксі
        async with session.post(GEMINI_URL, json=payload, timeout=20) as resp:
            if resp.status == 200:
                data = await resp.json()
                answer = data['candidates'][0]['content']['parts'][0]['text']
                await wait_msg.edit_text(f"✨ <b>Прогноз:</b>\n\n{answer}", parse_mode="HTML")
            else:
                await wait_msg.edit_text(f"❌ Помилка API (Статус: {resp.status})")
