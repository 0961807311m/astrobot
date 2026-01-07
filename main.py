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
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Налаштування ---
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

# Список керівників для фільтрації
MANAGERS_NAMES = [
    "Костюк Леся", "Склярук Анатолій", "Квартюк Іван", "Коваль Мирослава", "Селіверстов Олег",
    "Хоха", "Полігас Андрій", "Козак Олег", "Лиховид Сергій Миколайович", "Маснюк Олександр",
    "Москаленко Вова", "Людяний Олександр", "Лиховид Юра", "Кравець Михайло", "Влага Анатолій",
    "Рутковська Діана", "Манченко Сергій", "Кушнір Андрій", "Склярук Тетяна", "Островий Сергій",
    "Семеніхін Олексій", "Кравченко Ігор", "Бойко Тетяна", "Влага Ганна"
]

class BotStates(StatesGroup):
    waiting_for_employee_data = State()
    waiting_for_employee_role = State()
    waiting_for_task_name = State()
    waiting_for_route_data = State()

# --- База даних ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, shift_type TEXT DEFAULT 'day');")
    cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE, role TEXT DEFAULT 'Працівник');")
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

# --- Блок: Дні народження ---
@dp.message(F.text == "🎂 Дні народження")
async def bday_m(m: types.Message):
    t = datetime.now().strftime("%m-%d"); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (t,))
    rows = cur.fetchall(); cur.close(); conn.close()
    msg = "Сьогодні іменинників немає." if not rows else "🎉 Сьогодні іменинник: " + ", ".join([r[0] for r in rows])
    kb = InlineKeyboardBuilder().button(text="➕ Додати", callback_data="e_add").button(text="📜 Список", callback_data="e_list").button(text="🗑 Видалити", callback_data="e_del_l").adjust(2, 1)
    await m.answer(msg, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "e_list")
async def e_list(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name, birth_date FROM employees ORDER BY EXTRACT(MONTH FROM birth_date), EXTRACT(DAY FROM birth_date)")
    rows = cur.fetchall(); cur.close(); conn.close()
    res = {"Керівники": [], "Працівники": []}
    for name, date in rows:
        formatted = f"{date.strftime('%d.%m')} — {name}"
        if any(m_name in name for m_name in MANAGERS_NAMES): res["Керівники"].append(formatted)
        else: res["Працівники"].append(formatted)
    txt = "📜 **СПИСОК:**\n\n⭐ **КЕРІВНИКИ:**\n" + ("-" if not res["Керівники"] else "\n".join(res["Керівники"]))
    txt += "\n\n👥 **ПРАЦІВНИКИ:**\n" + ("-" if not res["Працівники"] else "\n".join(res["Працівники"]))
    await c.message.answer(txt, parse_mode="Markdown"); await c.answer()

@dp.callback_query(F.data == "e_add")
async def e_add(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Формат: Прізвище Ім'я - ДД.ММ.РРРР"); await state.set_state(BotStates.waiting_for_employee_data)

@dp.message(BotStates.waiting_for_employee_data)
async def e_save(m: types.Message, state: FSMContext):
    try:
        p = m.text.split(" - "); d = datetime.strptime(p[1].strip(), "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("INSERT INTO employees (full_name, birth_date) VALUES (%s, %s)", (p[0].strip(), d))
        conn.commit(); cur.close(); conn.close()
        await m.answer("✅ Додано!"); await state.clear()
    except: await m.answer("❌ Помилка. Формат: Прізвище Ім'я - 01.01.1990")

@dp.callback_query(F.data == "e_del_l")
async def e_del_l(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, full_name FROM employees ORDER BY full_name"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for eid, name in rows: kb.button(text=f"🗑 {name}", callback_data=f"ed_{eid}")
    kb.adjust(1); await c.message.edit_text("Виберіть для видалення:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("ed_"))
async def e_del_do(c: types.CallbackQuery):
    eid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM employees WHERE id = %s", (eid,)); conn.commit(); cur.close(); conn.close()
    await c.answer("Видалено"); await e_list(c)

# --- Блок: Завдання ---
async def t_kb():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title, is_done FROM tasks ORDER BY id ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for tid, title, done in rows: kb.button(text=f"{'✅' if done else '⬜'} {title}", callback_data=f"tgl_{tid}")
    kb.adjust(1).row(types.InlineKeyboardButton(text="➕ Додати", callback_data="t_add"), types.InlineKeyboardButton(text="🗑 Видалити", callback_data="t_del"))
    return kb.as_markup()

@dp.message(F.text == "📋 Завдання на зміну")
async def show_t(m: types.Message): await m.answer("Завдання:", reply_markup=await t_kb())

@dp.callback_query(F.data.startswith("tgl_"))
async def tgl(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = %s", (tid,)); conn.commit(); cur.close(); conn.close()
    await c.message.edit_reply_markup(reply_markup=await t_kb())

@dp.callback_query(F.data == "t_add")
async def t_add_c(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть завдання:"); await state.set_state(BotStates.waiting_for_task_name)

@dp.message(BotStates.waiting_for_task_name)
async def t_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO tasks (title) VALUES (%s)", (m.text,)); conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Завдання додано!"); await state.clear()

# --- Блок: Маршрути ---
@dp.message(F.text == "🚍 Маршрути")
async def show_r(m: types.Message):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT info FROM routes ORDER BY id ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    txt = "🚍 **Маршрути:**\n\n" + ("-" if not rows else "\n".join([f"📍 {r[0]}" for r in rows]))
    kb = InlineKeyboardBuilder().button(text="➕ Додати", callback_data="r_add").button(text="🗑 Видалити", callback_data="r_del").adjust(2)
    await m.answer(txt, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "r_add")
async def r_add_c(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Пришліть дані маршруту:"); await state.set_state(BotStates.waiting_for_route_data)

@dp.message(BotStates.waiting_for_route_data)
async def r_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO routes (info) VALUES (%s)", (m.text,)); conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Маршрут додано!"); await state.clear()

# --- Блок: Зміна ---
@dp.message(F.text == "⚙️ Зміна")
async def shift_m(m: types.Message):
    kb = InlineKeyboardBuilder().button(text="☀️ День", callback_data="s_day").button(text="🌙 Ніч", callback_data="s_night").adjust(1)
    await m.answer("Оберіть вашу зміну:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("s_"))
async def s_set(c: types.CallbackQuery):
    s = "day" if "day" in c.data else "night"
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE users SET shift_type = %s WHERE user_id = %s", (s, c.from_user.id)); conn.commit(); cur.close(); conn.close()
    await c.answer(f"Встановлено: {s}"); await c.message.answer(f"✅ Графік оновлено на: {s}")

# --- Системні хендлери ---
@dp.message(Command("start"))
async def start(m: types.Message):
    init_db()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", (m.from_user.id, m.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await m.answer("👋 Бот активний!", reply_markup=main_menu())

@dp.message()
async def any_msg(m: types.Message):
    await m.answer("Використовуйте кнопки меню 👇", reply_markup=main_menu())

async def reminders():
    now = datetime.now()
    if now.weekday() > 5: return
    t = now.strftime("%H:%M")
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("SELECT user_id, shift_type FROM users"); users = cur.fetchall(); cur.close(); conn.close()
        for uid, stype in users:
            if (stype == 'day' and t == "07:43") or (stype == 'night' and t == "16:43"):
                try: await bot.send_message(uid, "Вітаю! Яка кількість працівників сьогодні?")
                except: pass
    except: pass

async def main():
    init_db(); await bot.delete_webhook(drop_pending_updates=True)
    scheduler.add_job(reminders, "interval", minutes=1); scheduler.start()
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
