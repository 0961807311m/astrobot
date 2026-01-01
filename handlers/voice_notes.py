import os
import aiohttp
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database as db

router = Router()

API_KEY = "AIzaSyDcuDGVMEdV6ICTk5eDpkYcYml2FmvkmHg"
GEMINI_VOICE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
PROXY_URL = "http://proxy.server:3128"

class VoiceState(StatesGroup):
    waiting_for_voice = State()

@router.message(F.text == "📝 Завдання на зміну")
async def start_voice_note(message: types.Message, state: FSMContext):
    tasks = db.get_tasks(message.from_user.id)

    msg = "<b>📋 Твій список завдань:</b>\n\n"
    if tasks:
        for t_id, text, status in tasks:
            msg += f"☐ {text}\n"
    else:
        msg += "Список порожній. 🏖"

    msg += "\n\n🎤 <b>Запиши голосове</b>, щоб додати нові завдання на зміну. Я розшифрую їх автоматично!"
    await message.answer(msg, parse_mode="HTML")
    await state.set_state(VoiceState.waiting_for_voice)

@router.message(VoiceState.waiting_for_voice, F.voice)
async def handle_voice(message: types.Message, bot: Bot, state: FSMContext):
    wait_msg = await message.answer("⏳ <i>Слухаю та розшифровую...</i>", parse_mode="HTML")

    # 1. Отримуємо файл голосового
    file_id = message.voice.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"

    # 2. Завантажуємо аудіо через проксі
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url, proxy=PROXY_URL) as resp:
            if resp.status == 200:
                audio_data = await resp.read()

                # 3. Відправляємо в Gemini (Мультимодальний запит)
                import base64
                audio_b64 = base64.b64encode(audio_data).decode('utf-8')

                payload = {
                    "contents": [{
                        "parts": [
                            {"text": "Перетвори це аудіо в короткий список завдань. Пиши тільки пункти через кому, без вступу."},
                            {"inline_data": {"mime_type": "audio/ogg", "data": audio_b64}}
                        ]
                    }]
                }

                async with session.post(GEMINI_VOICE_URL, json=payload, proxy=PROXY_URL) as ai_resp:
                    if ai_resp.status == 200:
                        res = await ai_resp.json()
                        raw_tasks = res['candidates'][0]['content']['parts'][0]['text']

                        # Зберігаємо кожен пункт як окреме завдання
                        task_list = raw_tasks.split(',')
                        for item in task_list:
                            if item.strip():
                                db.add_task(message.from_user.id, item.strip())

                        await wait_msg.edit_text("✅ Завдання додано до списку!")
                    else:
                        await wait_msg.edit_text("❌ Не вдалося розшифрувати аудіо.")
            else:
                await wait_msg.edit_text("❌ Помилка завантаження файлу.")

    await state.clear()
