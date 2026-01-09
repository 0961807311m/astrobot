import os
import asyncio
import logging
import psycopg2
import pytz
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Налаштування ---
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
KYIV_TZ = pytz.timezone("Europe/Kyiv")

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=KYIV_TZ)

MANAGERS_NAMES = [
    "Костюк Леся", "Склярук Анатолій", "Квартюк Іван", "Коваль Мирослава", "Селіверстов Олег",
    "Хоха", "Полігас Андрій", "Козак Олег", "Лиховид Сергій Миколайович", "Маснюк Олександр",
    "Москаленко Вова", "Людяний Олександр", "Лиховид Юра", "Кравець Михайло", "Влага Анатолій",
    "Рутковська Діана", "Манченко Сергій", "Кушнір Андрій", "Склярук Тетяна", "Островий Сергій",
    "Семеніхін Олексій", "Кравченко Ігор", "Бойко Тетяна", "Влага Ганна"
]

class BotStates(StatesGroup):
    waiting_for_employee_data = State()
    waiting_for_task_name = State()
    waiting_for_route_data = State()

def init_db():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, shift_type TEXT DEFAULT 'day');")
    cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE);")
    cur.execute("CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT, is_done BOOLEAN DEFAULT FALSE);")
    cur.execute("CREATE TABLE IF NOT EXISTS routes (id SERIAL PRIMARY KEY, info TEXT);")
    conn.commit(); cur.close(); conn.close()

def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Завдання на зміну")
    builder.button(text="🚍 Маршрути")
    builder.button(text="⚙️ Зміна")
    builder.button(text="🎂 Дні народження")
    builder.adjust(1, 1, 2)
    return builder.as_markup(resize_keyboard=True)

# --- Блок: ЗАВДАННЯ (З видаленням та фінішем) ---
async def get_tasks_kb():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title, is_done FROM tasks ORDER BY id ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for tid, title, done in rows:
        kb.button(text=f"{'✅' if done else '⬜'} {title}", callback_data=f"tgl_{tid}")
    kb.adjust(1)
    kb.row(types.InlineKeyboardButton(text="➕ Додати", callback_data="t_add"),
           types.InlineKeyboardButton(text="🗑 Видалити", callback_data="t_del_menu"))
    return kb.as_markup()

@dp.message(F.text == "📋 Завдання на зміну")
async def show_tasks(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("Список завдань:", reply_markup=await get_tasks_kb())

@dp.callback_query(F.data.startswith("tgl_"))
async def toggle_task(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = %s", (tid,))
    conn.commit()
    
    # Перевірка чи всі виконані
    cur.execute("SELECT count(*) FROM tasks WHERE is_done = FALSE")
    remaining = cur.fetchone()[0]
    cur.close(); conn.close()
    
    await c.message.edit_reply_markup(reply_markup=await get_tasks_kb())
    
    if remaining == 0:
        await c.message.answer("🎉 Вітаю! Усі завдання на сьогодні виконано!")
    await c.answer()

@dp.callback_query(F.data == "t_add")
async def t_add_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Напишіть нове завдання:"); await state.set_state(BotStates.waiting_for_task_name)

@dp.message(BotStates.waiting_for_task_name)
async def t_add_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO tasks (title) VALUES (%s)", (m.text,)); conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Додано!", reply_markup=main_menu()); await state.clear()

@dp.callback_query(F.data == "t_del_menu")
async def t_del_menu(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title FROM tasks"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for tid, title in rows: kb.button(text=f"❌ {title}", callback_data=f"tdel_{tid}")
    kb.adjust(1); kb.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="t_back"))
    await c.message.edit_text("Оберіть завдання для видалення:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("tdel_"))
async def t_del_exec(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (tid,)); conn.commit(); cur.close(); conn.close()
    await c.answer("Видалено"); await c.message.edit_text("Завдання:", reply_markup=await get_tasks_kb())

@dp.callback_query(F.data == "t_back")
async def t_back(c: types.CallbackQuery):
    await c.message.edit_text("Список завдань:", reply_markup=await get_tasks_kb())

# --- Інші функції (ДН, Маршрути, Зміна) залишаються з попереднього коду ---
# (Для економії місця додайте їх самостійно або використовуйте цей файл як основу)

@dp.message(Command("start"))
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear(); init_db()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", (m.from_user.id, m.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await m.answer("👋 Бот готовий!", reply_markup=main_menu())

async def check_reminders():
    now = datetime.now(KYIV_TZ)
    if now.weekday() > 4: return
    t = now.strftime("%H:%M")
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("SELECT user_id, shift_type FROM users"); rows = cur.fetchall(); cur.close(); conn.close()
        for uid, s in rows:
            if (s == 'day' and t == "07:43") or (s == 'night' and t == "16:43"):
                await bot.send_message(uid, "🔔 Нагадування: Подайте кількість персоналу!")
    except: pass

async def main():
    init_db(); await bot.delete_webhook(drop_pending_updates=True)
    scheduler.add_job(check_reminders, "interval", minutes=1); scheduler.start()
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
