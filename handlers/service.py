import os
import aiohttp
from aiogram import Router, F, types
from aiogram.filters import CommandStart

router = Router()

API_KEY = os.getenv("API_KEY", "").strip()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="✨ Порада дня")],
        [types.KeyboardButton(text="🎂 Дні народження"), types.KeyboardButton(text="🛠 Список моделей ШІ")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("✅ Бот онлайн. Натисніть <b>'Список моделей ШІ'</b>, щоб побачити доступні назви.", reply_markup=keyboard, parse_mode="HTML")

@router.message(F.text == "🛠 Список моделей ШІ")
async def list_models(message: types.Message):
    if not API_KEY:
        await message.answer("❌ API_KEY не налаштовано.")
        return

    wait_msg = await message.answer("🔍 Запитую список доступних моделей у Google...")
    
    # Використовуємо спеціальний ендпоінт для переліку моделей
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                data = await resp.json()
                if resp.status == 200:
                    models = data.get("models", [])
                    # Фільтруємо тільки ті, що підтримують генерацію контенту
                    names = [m["name"].replace("models/", "") for m in models if "generateContent" in m.get("supportedGenerationMethods", [])]
                    
                    if names:
                        response_text = "✅ <b>Доступні моделі:</b>\n\n" + "\n".join([f"• <code>{name}</code>" for name in names])
                        response_text += "\n\nСкопіюйте назву, яка вам подобається (напр. gemini-1.5-flash-latest)."
                        await wait_msg.edit_text(response_text, parse_mode="HTML")
                    else:
                        await wait_msg.edit_text("😕 Моделей не знайдено, але ключ спрацював.")
                else:
                    err = data.get("error", {}).get("message", "Unknown error")
                    await wait_msg.edit_text(f"❌ Помилка {resp.status}: {err}")
        except Exception as e:
            await wait_msg.edit_text(f"⚠️ Помилка: {str(e)}")
