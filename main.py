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
from aiogram.types import BufferedInputFile
from aiohttp import web
from openai import OpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Налаштування логування ---
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

# --- База даних (З автоматичним виправленням структури) ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Створення основних таблиць
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT);")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE);")
        cur.execute("CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT, is_done BOOLEAN DEFAULT FALSE);")
        
        # ДОДАВАННЯ КОЛОНКИ, ЯКОЇ НЕ ВИСТАЧАЛО
        cur.execute("""
            DO $$ 
            BEGIN 
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                               WHERE table_name='users' AND column_name='shift_type') THEN
                    ALTER TABLE users ADD COLUMN shift_type TEXT DEFAULT 'day';
                END IF;
            END $$;
        """)
        
        conn.commit()
        cur.close(); conn.close()
        logging.info("✅ База даних перевірена та готова")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# --- Функції Нагадувань ---
async def send_shift_reminder(user_id, shift_type):
    text = "Вітаю, скільки на сьогодні працівників?" if shift_type == "day" else "Вітаю, яка кількість працівників?"
    try:
        await bot.send_message(user_id, text)
    except Exception as e:
        logging.error(f"Помилка відправки нагадування {user_id}: {e}")

async def check_and_send_reminders():
    now = datetime.now()
    if now.weekday() > 5: return # Працюємо Пн-Сб (0-5)
    
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
    builder.button(text="☀️ Тиждень День (07:43)", callback_data="set_shift_day")
    builder.button(text="🌙 Тиждень Ніч (16:43)", callback_data="set_shift_night")
    builder.button(text="🚀 ТЕСТ", callback_data="test_shift_now")
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
        builder.row(types.InlineKeyboardButton(text="🎉 Всі задачі виконано! Вдалої зміни!", callback_data="fin_shift"))
    builder.row(types.InlineKeyboardButton(text="➕ Додати", callback_data="task_add"),
                types.InlineKeyboardButton(text="🗑 Видалити", callback_data="task_edit"))
    return builder.as_markup()

# --- Хендлери Зміни ---
@dp.message(F.text == "⚙️ Зміна")
async def cmd_shift(message: types.Message):
    await message.answer("Оберіть графік нагадувань (Пн-Сб):", reply_markup=shift_kb())

@dp.callback_query(F.data.startswith("set_shift_"))
async def set_shift_type(callback: types.CallbackQuery):
    s_type = "day" if "day" in callback.data else "night"
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE users SET shift_type = %s WHERE user_id = %s", (s_type, callback.from_user.id))
    conn.commit(); cur.close(); conn.close()
    time_str = "07:43" if s_type == "day" else "16:43"
    await callback.message.edit_text(f"✅ Встановлено: {'День' if s_type=='day' else 'Ніч'} ({time_str})")

@dp.callback_query(F.data == "test_shift_now")
async def test_shift_call(callback: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT shift_type FROM users WHERE user_id = %s", (callback.from_user.id,))
    res = cur.fetchone(); cur.close(); conn.close()
    s = res[0] if res else "day"
    await send_shift_reminder(callback.from_user.id, s)
    await callback.answer("Тестове нагадування надіслано!")

# --- Хендлери Завдань ---
@dp.message(F.text == "📋 Завдання на зміну")
async def show_t(message: types.Message):
    await message.answer("Список завдань:", reply_markup=await tasks_kb())

@dp.callback_query(F.data.startswith("tgl_"))
async def toggle_task_status(callback: types.CallbackQuery):
    tid = int(callback.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = %s", (tid,))
    conn.commit(); cur.close(); conn.close()
    await callback.message.edit_reply_markup(reply_markup=await tasks_kb())

@dp.callback_query(F.data == "fin_shift")
async def finish_shift(callback: types.CallbackQuery):
    await callback.message.answer("🌟 Вдалої зміни! Завдання скинуто.")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = FALSE")
    conn.commit(); cur.close(); conn.close()
    await callback.message.edit_reply_markup(reply_markup=await tasks_kb())

# --- Інші Хендлери ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    init_db()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (m.from_user.id, m.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await m.answer("👋 Бот активовано!", reply_markup=main_menu())

@dp.message(F.text == "🎂 Дні народження")
async def bday_show(m: types.Message):
    t = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (t,))
    w = cur.fetchall(); cur.close(); conn.close()
    msg = "Сьогодні іменинників немає." if not w else "🎂 Сьогодні:\n" + "\n".join([x[0] for x in w])
    kb = InlineKeyboardBuilder().button(text="➕ Додати", callback_data="emp_add").as_markup()
    await m.answer(msg, reply_markup=kb)

@dp.callback_query(F.data == "emp_add")
async def e_add_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Прізвище Ім'я - ДД.ММ.РРРР")
    await state.set_state(BotStates.waiting_for_employee_data)

@dp.message(BotStates.waiting_for_employee_data)
async def e_save(m: types.Message, state: FSMContext):
    try:
        p = m.text.split(" - ")
        d = datetime.strptime(p[1].strip(), "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("INSERT INTO employees (full_name, birth_date) VALUES (%s, %s)", (p[0].strip(), d))
        conn.commit(); cur.close(); conn.close()
        await m.answer("✅ Працівника додано!"); await state.clear()
    except: await m.answer("❌ Помилка! Спробуйте ще раз за форматом.")

@dp.callback_query(F.data == "task_add")
async def t_add_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Напишіть назву задачі:"); await state.set_state(BotStates.waiting_for_task_name)

@dp.message(BotStates.waiting_for_task_name)
async def t_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO tasks (title) VALUES (%s)", (m.text,))
    conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Задача додана!"); await state.clear()

@dp.callback_query(F.data == "task_edit")
async def t_edit_list(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title FROM tasks"); t = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for x in t: kb.button(text=f"🗑 {x[1]}", callback_data=f"del_{x[0]}")
    kb.adjust(1).row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_t"))
    await c.message.edit_text("Видалення задач:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("del_"))
async def t_delete(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (tid,))
    conn.commit(); cur.close(); conn.close()
    await t_edit_list(c)

@dp.callback_query(F.data == "back_to_t")
async def t_back(c: types.CallbackQuery):
    await c.message.edit_text("Список завдань:", reply_markup=await tasks_kb())

@dp.message(F.text == "💬 Поговорити")
async def chat_msg(m: types.Message):
    await m.answer("Напишіть своє питання:")

@dp.message(F.text)
async def handle_ai_chat(m: types.Message):
    await bot.send_chat_action(m.chat.id, "typing")
    try:
        res = client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free", 
            messages=[{"role": "user", "content": m.text}],
            timeout=15.0
        )
        await m.answer(res.choices[0].message.content)
    except:
        await m.answer("ШІ тимчасово недоступний. Спробуйте пізніше.")

# --- Запуск ---
async def main():
    init_db()
    # Захист від подвійного запуску
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2)
    
    # Запуск планувальника (перевірка кожну хвилину)
    scheduler.add_job(check_and_send_reminders, "interval", minutes=1)
    scheduler.start()

    # Веб-сервер для Render Health Check
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    
    logging.info("🚀 Бот запущений та готовий до роботи")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
