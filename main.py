import os
import asyncio
import logging
import psycopg2
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web
from openai import OpenAI

# --- Налаштування ---
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_KEY)

# --- Стани для введення даних ---
class UserProfile(StatesGroup):
    waiting_for_birthday = State()

# --- База даних ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    # Таблиця користувачів з датою народження
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            birthday DATE
        );
    """)
    # Таблиця працівників для привітань
    cur.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            full_name TEXT,
            birth_date DATE
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

# --- Клавіатура Головного Меню ---
def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💬 Поговорити")
    builder.button(text="✨ Порада дня")
    builder.button(text="🎂 Дні народження")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# --- Функція ШІ ---
async def ask_ai(system_prompt, user_prompt):
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Помилка ШІ: {e}"

# --- Хендлери ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    await message.answer(
        "Привіт! Я твій персональний асистент. 🚀\nЩоб поради були точними, натисніть '✨ Порада дня' і введіть свою дату народження.",
        reply_markup=main_menu_kb()
    )

# 1. Секція "Поговорити"
@dp.message(F.text == "💬 Поговорити")
async def talk_mode(message: types.Message):
    await message.answer("Я уважно слухаю. Про що хочеш поспілкуватися?")

# 2. Секція "Порада дня" (Логіка дати народження)
@dp.message(F.text == "✨ Порада дня")
async def astro_advice(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT birthday FROM users WHERE user_id = %s", (message.from_user.id,))
    res = cur.fetchone()
    cur.close()
    conn.close()

    if not res or not res[0]:
        await message.answer("Для розрахунку Матриці Долі мені потрібна твоя дата народження. Введи її у форматі: ДД.ММ.РРРР (наприклад, 15.05.1990)")
        await state.set_state(UserProfile.waiting_for_birthday)
    else:
        bday = res[0].strftime("%d.%m.%Y")
        await bot.send_chat_action(message.chat.id, "typing")
        
        system_msg = "Ти експерт з психології та енергетики. Твоє завдання дати пораду дня на основі дати народження (Матриця Долі). Не кажи 'я астролог'. Давай поради як коуч."
        user_msg = f"""
        Моя дата народження: {bday}. Сьогодні: {datetime.now().strftime('%d.%m.%Y')}.
        Напиши: 
        1. Загальна порада дня.
        2. Список 'Чого очікувати'.
        3. Список 'Чого уникати'.
        4. Енергетика дня в балах (від 1 до 100).
        Пиши коротко, мотивувально, українською мовою.
        """
        advice = await ask_ai(system_msg, user_msg)
        await message.answer(f"✨ **Твоя персональна порада:**\n\n{advice}", parse_mode="Markdown")

@dp.message(UserProfile.waiting_for_birthday)
async def process_birthday(message: types.Message, state: FSMContext):
    try:
        bday = datetime.strptime(message.text, "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("UPDATE users SET birthday = %s WHERE user_id = %s", (bday, message.from_user.id))
        if cur.rowcount == 0:
            cur.execute("INSERT INTO users (user_id, username, birthday) VALUES (%s, %s, %s)", 
                        (message.from_user.id, message.from_user.username, bday))
        conn.commit()
        cur.close()
        conn.close()
        await message.answer("✅ Дату збережено! Тепер натисніть '✨ Порада дня' ще раз.", reply_markup=main_menu_kb())
        await state.clear()
    except ValueError:
        await message.answer("❌ Неправильний формат. Спробуй ще раз: ДД.ММ.РРРР")

# 3. Секція "Дні народження працівників"
@dp.message(F.text == "🎂 Дні народження")
async def check_birthdays(message: types.Message):
    today = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
    workers = cur.fetchall()
    cur.close()
    conn.close()

    if workers:
        text = "🎉 **Сьогодні святкують:**\n" + "\n".join([f"🎂 {w[0]}" for w in workers])
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer("Сьогодні немає іменинників серед працівників. ✨")

# --- Веб-сервер та запуск ---
async def handle_ping(request): return web.Response(text="OK")

async def main():
    init_db()
    app = web.Application(); app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
