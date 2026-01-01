import aiohttp
import base64
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import database as db

router = Router()

API_KEY = "AIzaSyCacI5LRq7QbHKtdKRv9s-IAF3orgeYpbw"
MODEL_ID = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent?key={API_KEY}"
PROXY_URL = "http://proxy.server:3128"

class ShiftState(StatesGroup):
    waiting_for_voice = State()

def get_tasks_keyboard(user_id):
    tasks = db.get_tasks(user_id)
    buttons = [[InlineKeyboardButton(text=f"✅ {t[1]}", callback_data=f"done_{t[0]}")] for t in tasks]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(F.text == "📝 Завдання на зміну")
async def show_shift_tasks(message: types.Message, state: FSMContext):
    keyboard = get_tasks_keyboard(message.from_user.id)
    await message.answer("📋 <b>Твої завдання:</b>\n\n🎤 Запиши голос для нових завдань.", reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(ShiftState.waiting_for_voice)

@router.message(ShiftState.waiting_for_voice, F.voice)
async def process_voice_tasks(message: types.Message, bot: Bot, state: FSMContext):
    wait_msg = await message.answer("⏳ <i>Обробка аудіо...</i>", parse_mode="HTML")
    file = await bot.get_file(message.voice.file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url, proxy=PROXY_URL) as resp:
            if resp.status == 200:
                audio_data = base64.b64encode(await resp.read()).decode('utf-8')
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": "Перетвори аудіо на список завдань через крапку з комою. Тільки текст."},
                            {"inline_data": {"mime_type": "audio/ogg", "data": audio_data}}
                        ]
                    }]
                }
                async with session.post(GEMINI_URL, json=payload, proxy=PROXY_URL) as ai_resp:
                    if ai_resp.status == 200:
                        data = await ai_resp.json()
                        text = data['candidates'][0]['content']['parts'][0]['text']
                        for t in text.split(';'):
                            if t.strip(): db.add_task(message.from_user.id, t.strip())
                        await wait_msg.edit_text("✅ Завдання додано!", reply_markup=get_tasks_keyboard(message.from_user.id))
                    else:
                        await wait_msg.edit_text(f"❌ Помилка ШІ: {ai_resp.status}")
            else:
                await wait_msg.edit_text("❌ Помилка файлу.")
    await state.clear()