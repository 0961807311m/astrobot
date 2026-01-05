import os
import asyncio
import logging
import psycopg2
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web
from openai import OpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Конфігурація ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("OPENROUTER_API_KEY") 
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Клієнт ШІ (без повторів для швидкого fallback)
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
    max_retries=0 
)

# --- Стани (FSM) ---
class BotStates(StatesGroup):
    waiting_for_user_birthday = State()
    waiting_for_employee_data = State()

# --- База даних ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, birthday DATE);")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday DATE;")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE);")
        conn.commit()
        cur.close(); conn.close()
        logging.info("✅ БД ініціалізована")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# --- Робота з ШІ ---
async def ask_ai(system_prompt, user_prompt):
    models = [
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "gryphe/mythomax-l2-13b:free"
    ]
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                extra_headers={"HTTP-Referer": "https://render.com", "X-Title": "AstroBot_v5"},
                timeout=10.0 
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.warning(f"⚠️ {model} зайнята. Спроба наступної...")
            await asyncio.sleep(0.5)
            continue 
    return "⚠️ ШІ-лінії перевантажені. Спробуйте через 30 секунд."

# --- Автоматичне привітання ---
async def daily_birthday_check():
    today = datetime.now().strftime("%m-%d")
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
        workers = cur.fetchall()
        if workers:
            cur.execute("SELECT user_id FROM users")
            all_users = cur.fetchall()
            names = ", ".join([w[0] for w in workers])
            text = f"🎉 **Сьогоднішні іменинники:**\n\n🎂 {names}\n\nНе забудьте привітати колег! ✨"
            for user in all_users:
                try: await bot.send_message(user[0], text, parse_mode="Markdown")
                except: continue
        cur.close(); conn.close()
    except Exception as e: logging.error(f"❌ Помилка розсилки: {e}")

# --- Клавіатури ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💬 Поговорити")
    builder.button(text="✨ Порада дня")
    builder.button(text="🎂 Дні народження")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

def employees_inline():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати іменинника", callback_data="add_employee")
    return builder.as_markup()

# --- Хендлери ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (message.from_user.id, message.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await message.answer("🚀 Бот запущений! Оберіть розділ:", reply_markup=main_menu())

@dp.message(F.text == "✨ Порада дня")
async def astro_handler(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT birthday FROM users WHERE user_id = %s", (message.from_user.id,))
    res = cur.fetchone(); cur.close(); conn.close()
    if not res or not res[0]:
        await message.answer("Введіть вашу дату народження (ДД.ММ.РРРР):")
        await state.set_state(BotStates.waiting_for_user_birthday)
    else:
        await bot.send_chat_action(message.chat.id, "typing")
        ans = await ask_ai("Ти коуч. Дай пораду за Матрицею Долі.", f"Дата: {res[0].strftime('%d.%m.%Y')}. Напиши пораду дня.")
        await message.answer(ans)

@dp.message(BotStates.waiting_for_user_birthday)
async def set_user_bday(message: types.Message, state: FSMContext):
    try:
        bday = datetime.strptime(message.text, "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("UPDATE users SET birthday = %s WHERE user_id = %s", (bday, message.from_user.id))
        conn.commit(); cur.close(); conn.close()
        await message.answer("✅ Дата збережена! Натисніть кнопку 'Порада дня' ще раз.", reply_markup=main_menu())
        await state.clear()
    except: await message.answer("❌ Формат: ДД.ММ.РРРР")

@dp.message(F.text == "🎂 Дні народження")
async def bdays_menu(message: types.Message):
    today = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
    workers = cur.fetchall(); cur.close(); conn.close()
    text = "Сьогодні іменинників немає. ✨" if not workers else "🎉 Сьогодні святкують:\n" + "\n".join([f"🎂 {w[0]}" for w in workers])
    await message.answer(text, reply_markup=employees_inline())

@dp.callback_query(F.data == "add_employee")
async def start_add_employee(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Надішліть дані працівника одним повідомленням у форматі:\n\n**Прізвище Ім'я - ДД.ММ.РРРР**\n\nПриклад: Олександр Коваленко - 15.05.1990")
    await state.set_state(BotStates.waiting_for_employee_data)
    await callback.answer()

@dp.message(BotStates.waiting_for_employee_data)
async def save_employee(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split(" - ")
        name = parts[0].strip()
        bday = datetime.strptime(parts[1].strip(), "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("INSERT INTO employees (full_name, birth_date) VALUES (%s, %s)", (name, bday))
        conn.commit(); cur.close(); conn.close()
        await message.answer(f"✅ Працівника {name} успішно додано!", reply_markup=main_menu())
        await state.clear()
    except: await message.answer("❌ Помилка! Дотримуйтесь формату: Ім'я - ДД.ММ.РРРР")

@dp.message(F.text == "💬 Поговорити")
async def talk_info(message: types.Message):
    await message.answer("Просто пиши будь-яке запитання, і я відповім!")

@dp.message(F.text)
async def chat_handler(message: types.Message):
    await bot.send_chat_action(message.chat.id, "typing")
    ans = await ask_ai("Ти корисний помічник.", message.text)
    await message.answer(ans)

# --- Старт ---
async def main():
    init_db()
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    scheduler.add_job(daily_birthday_check, "cron", hour=9, minute=0)
    scheduler.start()
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
