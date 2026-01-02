@router.message(F.text == "🛠 Діагностика ШІ")
async def check_ai_status(message: types.Message):
    wait_msg = await message.answer("🔍 <b>Спроба з'єднання з Google AI...</b>", parse_mode="HTML")
    
    # Спробуємо версію v1 (стабільну) замість v1beta
    TEST_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": "Привіт"}]}]}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(TEST_URL, json=payload, headers=headers, timeout=15) as resp:
                raw_text = await resp.text()
                if resp.status == 200:
                    await wait_msg.edit_text("✅ <b>Gemini API: 200 OK</b>\nЗв'язок встановлено!", parse_mode="HTML")
                elif resp.status == 403:
                    await wait_msg.edit_text(f"❌ <b>Помилка 403</b>\nGoogle відхиляє ключ. Перевірте, чи створено ключ у Google AI Studio саме для Gemini.")
                else:
                    await wait_msg.edit_text(f"❓ <b>Статус: {resp.status}</b>\n{raw_text[:50]}")
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ <b>Помилка:</b> {str(e)[:50]}")
