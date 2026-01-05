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

# --- Стани ---
class UserProfile(StatesGroup):
    waiting_for_birthday = State()

# --- Функція створення клавіатури ---
def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    # Додаємо кнопки
    builder.button(text="💬 Поговорити")
    builder.button(text="✨ Порада дня")
    builder.button(text="🎂 Дні народження")
    # Налаштовуємо вигляд (2 кнопки в ряд, потім 1)
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True, input_field_placeholder="Оберіть розділ меню")

# --- База даних ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                birthday DATE
            );
        """)
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
        logging.info("✅ База даних готова")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

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
        return "⚠️ ШІ тимчасово недоступний."

# --- Хендлери ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    # Надсилаємо повідомлення з клавіатурою
    await message.answer(
        f"Привіт, {message.from_user.first_name}! 🚀\n\nЯ твій ШІ-помічник. Оберіть потрібний розділ нижче:",
        reply_markup=main_menu_kb()
    )

@dp.message(F.text == "💬 Поговорити")
async def talk_mode(message: types.Message):
    await message.answer("Я уважно слухаю. Напиши своє питання, і я відповім!")

@dp.message(F.text == "✨ Порада дня")
async def astro_advice(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT birthday FROM users WHERE user_id = %s", (message.from_user.id,))
    res = cur.fetchone()
    cur.close()
    conn.close()

    if not res or not res[0]:
        await message.answer("Для точної поради мені потрібна твоя дата народження. Введи її у форматі **ДД.ММ.РРРР** (наприклад: 25.10.1995)")
        await state.set_state(UserProfile.waiting_for_birthday)
    else:
        await bot.send_chat_action(message.chat.id, "typing")
        bday = res[0].strftime("%d.%m.%Y")
        system_msg = "Ти професійний коуч та психолог. Даєш поради на основі Матриці Долі, але не звучиш як ворожка. Твій тон — надихаючий та аналітичний."
        user_msg = f"Моя дата народження {bday}. Дай пораду на сьогодні {datetime.now().strftime('%d.%m.%Y')}. Напиши: 1. Порада дня. 2. Чого очікувати. 3. Чого уникати. 4. Енергія дня у балах (0-100). Українською."
        
        advice = await ask_ai(system_msg, user_msg)
        await message.answer(advice)

@dp.message(UserProfile.waiting_for_birthday)
async def save_bday(message: types.Message, state: FSMContext):
    try:
        bday = datetime.strptime(message.text, "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, birthday) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (user_id) DO UPDATE SET birthday = EXCLUDED.birthday
        """, (message.from_user.id, message.from_user.username, bday))
        conn.commit()
        cur.close()
        conn.close()
        await message.answer("✅ Дату збережено! Натисніть '✨ Порада дня' ще раз.", reply_markup=main_menu_kb())
        await state.clear()
    except ValueError:
        await message.answer("❌ Формат невірний. Напиши дату як ДД.ММ.РРРР (наприклад: 01.01.2000)")

@dp.message(F.text == "🎂 Дні народження")
async def check_bdays(message: types.Message):
    today = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
    workers = cur.fetchall()
    cur.close()
    conn.close()

    if workers:
        res = "🎉 **Сьогодні святкують:**\n\n" + "\n".join([f"🎂 {w[0]}" for w in workers])
        await message.answer(res)
    else:
        await message.answer("Сьогодні іменинників немає. ✨")

# --- Веб-сервер ---
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
