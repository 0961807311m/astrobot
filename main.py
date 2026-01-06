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
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY, max_retries=0)
scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

class BotStates(StatesGroup):
    waiting_for_employee_data = State()
    waiting_for_task_name = State()

# --- База даних ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, shift_type TEXT DEFAULT 'day');")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE);")
        cur.execute("CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT, is_done BOOLEAN DEFAULT FALSE);")
        conn.commit()
        cur.close(); conn.close()
        logging.info("✅ БД ініціалізована")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# --- Функції Нагадувань ---
async def send_shift_reminder(user_id, shift_type):
    if shift_type == "day":
        text = "Вітаю, скільки на сьогодні працівників?"
    else:
        text = "Вітаю, яка кількість працівників?"
    try:
        await bot.send_message(user_id, text)
    except Exception as e:
        logging.error(f"Не вдалося надіслати нагадування: {e}")

async def scheduled_reminder_task():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT user_id, shift_type FROM users")
    users = cur.fetchall(); cur.close(); conn.close()
    
    now = datetime.now()
    # Понеділок=0, Субота=5
    if now.weekday() <= 5: 
        current_time = now.strftime("%H:%M")
        for user_id, shift in users:
            if shift == "day" and current_time == "07:43":
                await send_shift_reminder(user_id, "day")
            elif shift == "night" and current_time == "16:43":
                await send_shift_reminder(user_id, "night")

# --- Клавіатури ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Завдання на зміну")
    builder.button(text="⚙️ Зміна")
    builder.button(text="🎂 Дні народження")
    builder.button(text="💬 Поговорити")
    builder.adjust(1, 2, 1)
    return builder.as_markup(resize_keyboard=True)

def shift_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="☀️ Тиждень День (07:43)", callback_data="set_shift_day")
    builder.button(text="🌙 Тиждень Ніч (16:43)", callback_data="set_shift_night")
    builder.button(text="🚀 ТЕСТ", callback_data="test_reminder")
    builder.adjust(1)
    return builder.as_markup()

async def tasks_keyboard():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title, is_done FROM tasks ORDER BY id ASC")
    tasks = cur.fetchall(); cur.close(); conn.close()
    builder = InlineKeyboardBuilder()
    all_done = len(tasks) > 0
    for tid, title, is_done in tasks:
        icon = "✅" if is_done else "⬜"
        if not is_done: all_done = False
        builder.button(text=f"{icon} {title}", callback_data=f"toggle_{tid}")
    builder.adjust(1)
    if all_done and tasks:
        builder.row(types.InlineKeyboardButton(text="🎉 Усі задачі виконано!", callback_data="finish_shift"))
    builder.row(types.InlineKeyboardButton(text="➕ Додати", callback_data="add_task"),
                types.InlineKeyboardButton(text="🗑 Видалити", callback_data="edit_tasks_list"))
    return builder.as_markup()

# --- Хендлери Зміни ---

@dp.message(F.text == "⚙️ Зміна")
async def shift_menu(message: types.Message):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT shift_type FROM users WHERE user_id = %s", (message.from_user.id,))
    res = cur.fetchone(); cur.close(); conn.close()
    current = "День" if res and res[0] == "day" else "Ніч"
    await message.answer(f"Поточний графік: **{current}**\nОберіть новий режим нагадувань (Пн-Сб):", reply_markup=shift_kb(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("set_shift_"))
async def set_shift(callback: types.CallbackQuery):
    new_shift = "day" if "day" in callback.data else "night"
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE users SET shift_type = %s WHERE user_id = %s", (new_shift, callback.from_user.id))
    conn.commit(); cur.close(); conn.close()
    await callback.message.edit_text(f"✅ Графік змінено на: {'День (07:43)' if new_shift=='day' else 'Ніч (16:43)'}")
    await callback.answer()

@dp.callback_query(F.data == "test_reminder")
async def test_reminder(callback: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT shift_type FROM users WHERE user_id = %s", (callback.from_user.id,))
    res = cur.fetchone(); cur.close(); conn.close()
    shift = res[0] if res else "day"
    await send_shift_reminder(callback.from_user.id, shift)
    await callback.answer("Тестове повідомлення надіслано!")

# --- Інші Хендлери ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (message.from_user.id, message.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await message.answer("👋 Асистент готовий!", reply_markup=main_menu())

@dp.message(F.text == "📋 Завдання на зміну")
async def show_tasks(message: types.Message):
    await message.answer("Завдання:", reply_markup=await tasks_keyboard())

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_task(callback: types.CallbackQuery):
    tid = int(callback.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = %s", (tid,))
    conn.commit(); cur.close(); conn.close()
    await callback.message.edit_reply_markup(reply_markup=await tasks_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "finish_shift")
async def finish_shift_call(callback: types.CallbackQuery):
    await callback.message.answer("🎉 Вдалої зміни! Задачі скинуто.")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = FALSE")
    conn.commit(); cur.close(); conn.close()
    await callback.answer()

@dp.message(F.text == "🎂 Дні народження")
async def bdays_menu(message: types.Message):
    today = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
    workers = cur.fetchall(); cur.close(); conn.close()
    text = "Сьогодні іменинників немає." if not workers else "🎉 Сьогодні:\n" + "\n".join([f"🎂 {w[0]}" for w in workers])
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати", callback_data="add_employee")
    await message.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "add_employee")
async def add_emp_call(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Формат: ПІБ - ДД.ММ.РРРР")
    await state.set_state(BotStates.waiting_for_employee_data)
    await callback.answer()

@dp.message(BotStates.waiting_for_employee_data)
async def save_employee(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split(" - ")
        name, bday = parts[0].strip(), datetime.strptime(parts[1].strip(), "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("INSERT INTO employees (full_name, birth_date) VALUES (%s, %s)", (name, bday))
        conn.commit(); cur.close(); conn.close()
        await message.answer(f"✅ Додано: {name}")
        await state.clear()
    except: await message.answer("❌ Формат невірний!")

@dp.callback_query(F.data == "add_task")
async def add_task_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть назву задачі:")
    await state.set_state(BotStates.waiting_for_task_name)
    await callback.answer()

@dp.message(BotStates.waiting_for_task_name)
async def save_task(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO tasks (title) VALUES (%s)", (message.text,))
    conn.commit(); cur.close(); conn.close()
    await message.answer("✅ Задача додана!")
    await state.clear()

@dp.callback_query(F.data == "edit_tasks_list")
async def edit_tasks_view(callback: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title FROM tasks")
    tasks = cur.fetchall(); cur.close(); conn.close()
    builder = InlineKeyboardBuilder()
    for tid, title in tasks: builder.button(text=f"❌ {title}", callback_data=f"del_task_{tid}")
    builder.adjust(1); builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_tasks"))
    await callback.message.edit_text("Видалити задачу:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("del_task_"))
async def delete_task(callback: types.CallbackQuery):
    tid = int(callback.data.split("_")[2])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (tid,))
    conn.commit(); cur.close(); conn.close()
    await edit_tasks_view(callback)

@dp.callback_query(F.data == "back_to_tasks")
async def back_to_tasks(callback: types.CallbackQuery):
    await callback.message.edit_text("Завдання:", reply_markup=await tasks_keyboard())

@dp.message(F.text == "💬 Поговорити")
async def chat_info(message: types.Message):
    await message.answer("Напишіть запитання:")

@dp.message(F.text)
async def handle_text(message: types.Message):
    await bot.send_chat_action(message.chat.id, "typing")
    # Проста обробка ШІ
    try:
        res = client.chat.completions.create(model="google/gemini-2.0-flash-exp:free", messages=[{"role": "user", "content": message.text}])
        await message.answer(res.choices[0].message.content)
    except: await message.answer("ШІ зараз недоступний.")

# --- Запуск ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2)
    
    # Нагадування щохвилини перевіряють час
    scheduler.add_job(scheduled_reminder_task, "interval", minutes=1)
    scheduler.start()

    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
