import aiohttp
import time
from aiogram import Router, F, types

router = Router()

# АКТУАЛЬНІ НАЛАШТУВАННЯ 2026
API_KEY = "AIzaSyCacI5LRq7QbHKtdKRv9s-IAF3orgeYpbw"
MODEL_ID = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={API_KEY}"
PROXY_URL = "http://proxy.server:3128"

@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 <b>Перевірка зв'язку з Gemini 2.0...</b>", parse_mode="HTML")

    results = []
    async with aiohttp.ClientSession() as session:
        # Тест проксі
        try:
            async with session.get("http://google.com", proxy=PROXY_URL, timeout=10) as resp:
                results.append(f"1. 🛰 <b>Проксі:</b> ✅ OK ({resp.status})")
        except:
            results.append("1. 🛰 <b>Проксі:</b> ❌ ПОМИЛКА")

        # Тест ШІ
        payload = {"contents": [{"parts": [{"text": "Hi"}]}]}
        try:
            async with session.post(GEMINI_URL, json=payload, proxy=PROXY_URL, timeout=15) as ai_resp:
                if ai_resp.status == 200:
                    results.append(f"2. 🤖 <b>Gemini API:</b> ✅ ГОТОВИЙ")
                else:
                    results.append(f"2. 🤖 <b>Gemini API:</b> ❌ СТАТУС {ai_resp.status}")
        except:
            results.append("2. 🤖 <b>Gemini API:</b> ❌ ТАЙМАУТ")

    await wait_msg.edit_text("\n".join(results), parse_mode="HTML")