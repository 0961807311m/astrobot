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

# --- Налаштування ---
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
    except Exception as e:
        logging.error(f"DB Error: {e}")

# --- Нагадування ---
async def send_shift_reminder(user_id, shift_type):
    text = "Вітаю, скільки на сьогодні працівників?" if shift_type == "day" else "Вітаю, яка кількість працівників?"
    try:
        await bot.send_message(user_id, text)
    except: pass

async def check_and_send_reminders():
    now = datetime.now()
    if now.weekday() > 5: return # Тільки Пн-Сб
    
    current_time = now.strftime("%H:%M")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT user_id, shift_type FROM users")
    users = cur.fetchall(); cur.close(); conn.close()

    for uid, shift in users:
        if shift == 'day' and current_time == "07:43":
            await send_shift_reminder(uid, "day")
        elif shift == 'night' and current_time == "16:43":
            await send_shift_reminder(uid, "night")

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
    builder.button(text="☀️ Тиждень День (07:43)", callback_data="set_day")
    builder.button(text="🌙 Тиждень Ніч (16:43)", callback_data="set_night")
    builder.button(text="🚀 ТЕСТ", callback_data="test_now")
    builder.adjust(1)
    return builder.as_markup()

async def tasks_kb():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title, is_done FROM tasks ORDER BY id ASC")
    tasks = cur.fetchall(); cur.close(); conn.close()
    builder = InlineKeyboardBuilder()
    all_done = len(tasks) > 0
    for tid, title, done in tasks:
        icon = "✅" if done else "⬜"
        if not done: all_done = False
        builder.button(text=f"{icon} {title}", callback_data=f"tgl_{tid}")
    builder.adjust(1)
    if all_done and tasks:
        builder.row(types.InlineKeyboardButton(text="🎉 Всі задачі виконано! Вдалої зміни!", callback_data="finish"))
    builder.row(types.InlineKeyboardButton(text="➕ Додати", callback_data="t_add"),
                types.InlineKeyboardButton(text="🗑 Видалити", callback_data="t_edit"))
    return builder.as_markup()

# --- Обробка Зміни ---
@dp.message(F.text == "⚙️ Зміна")
async def cmd_shift(message: types.Message):
    await message.answer("Оберіть ваш графік нагадувань (Пн-Сб):", reply_markup=shift_kb())

@dp.callback_query(F.data.startswith("set_"))
async def set_shift(callback: types.CallbackQuery):
    s = "day" if "day" in callback.data else "night"
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE users SET shift_type = %s WHERE user_id = %s", (s, callback.from_user.id))
    conn.commit(); cur.close(); conn.close()
    await callback.message.edit_text(f"✅ Встановлено: {'День (07:43)' if s=='day' else 'Ніч (16:43)'}")

@dp.callback_query(F.data == "test_now")
async def test_call(callback: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT shift_type FROM users WHERE user_id = %s", (callback.from_user.id,))
    res = cur.fetchone(); cur.close(); conn.close()
    shift = res[0] if res else "day"
    await send_shift_reminder(callback.from_user.id, shift)
    await callback.answer("Тест надіслано!")

# --- Обробка Завдань ---
@dp.message(F.text == "📋 Завдання на зміну")
async def show_t(message: types.Message):
    await message.answer("Завдання на зміну:", reply_markup=await tasks_kb())

@dp.callback_query(F.data.startswith("tgl_"))
async def toggle(callback: types.CallbackQuery):
    tid = int(callback.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = %s", (tid,))
    conn.commit(); cur.close(); conn.close()
    await callback.message.edit_reply_markup(reply_markup=await tasks_kb())

@dp.callback_query(F.data == "finish")
async def fin(callback: types.CallbackQuery):
    await callback.message.answer("🌟 Вдалої зміни! Задачі скинуто.")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = FALSE")
    conn.commit(); cur.close(); conn.close()
    await callback.message.edit_reply_markup(reply_markup=await tasks_kb())

# --- Решта функцій ---
@dp.message(Command("start"))
async def start(m: types.Message):
    init_db()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (m.from_user.id, m.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await m.answer("🚀 Бот запущений!", reply_markup=main_menu())

@dp.message(F.text == "🎂 Дні народження")
async def bday(m: types.Message):
    t = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (t,))
    w = cur.fetchall(); cur.close(); conn.close()
    msg = "Сьогодні іменинників немає." if not w else "🎂 Сьогодні:\n" + "\n".join([x[0] for x in w])
    kb = InlineKeyboardBuilder().button(text="➕ Додати", callback_data="emp_add").as_markup()
    await m.answer(msg, reply_markup=kb)

@dp.callback_query(F.data == "emp_add")
async def e_add(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Формат: ПІБ - ДД.ММ.РРРР")
    await state.set_state(BotStates.waiting_for_employee_data)

@dp.message(BotStates.waiting_for_employee_data)
async def e_save(m: types.Message, state: FSMContext):
    try:
        p = m.text.split(" - ")
        d = datetime.strptime(p[1].strip(), "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("INSERT INTO employees (full_name, birth_date) VALUES (%s, %s)", (p[0].strip(), d))
        conn.commit(); cur.close(); conn.close()
        await m.answer("✅ Додано!"); await state.clear()
    except: await m.answer("❌ Помилка формату!")

@dp.callback_query(F.data == "t_add")
async def t_add(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Назва задачі:"); await state.set_state(BotStates.waiting_for_task_name)

@dp.message(BotStates.waiting_for_task_name)
async def t_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO tasks (title) VALUES (%s)", (m.text,))
    conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Додано!"); await state.clear()

@dp.callback_query(F.data == "t_edit")
async def t_edit(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title FROM tasks"); t = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for x in t: kb.button(text=f"🗑 {x[1]}", callback_data=f"del_{x[0]}")
    kb.adjust(1).row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back"))
    await c.message.edit_text("Видалити задачу:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("del_"))
async def t_del(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (tid,))
    conn.commit(); cur.close(); conn.close()
    await t_edit(c)

@dp.callback_query(F.data == "back")
async def back(c: types.CallbackQuery):
    await c.message.edit_text("Завдання на зміну:", reply_markup=await tasks_kb())

@dp.message(F.text == "💬 Поговорити")
async def chat_msg(m: types.Message):
    await m.answer("Я слухаю...")

@dp.message(F.text)
async def ai_chat(m: types.Message):
    await bot.send_chat_action(m.chat.id, "typing")
    try:
        res = client.chat.completions.create(model="google/gemini-2.0-flash-exp:free", messages=[{"role": "user", "content": m.text}])
        await m.answer(res.choices[0].message.content)
    except: await m.answer("ШІ зараз недоступний.")

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2) # Пауза для уникнення Conflict Error
    
    scheduler.add_job(check_and_send_reminders, "interval", minutes=1)
    scheduler.start()

    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
