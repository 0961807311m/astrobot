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

# --- Налаштування логування ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
KYIV_TZ = pytz.timezone("Europe/Kyiv")

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=KYIV_TZ)

# Список керівників (для фільтрації в списку ДН)
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

# --- База даних ---
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

# --- Нагадування про персонал ---
async def check_reminders():
    now = datetime.now(KYIV_TZ)
    if now.weekday() > 4: return  # Не турбуємо у вихідні
    
    current_time = now.strftime("%H:%M")
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("SELECT user_id, shift_type FROM users"); users = cur.fetchall(); cur.close(); conn.close()
        
        for user_id, shift in users:
            if shift == 'day' and current_time == "07:43":
                await bot.send_message(user_id, "☀️ Вітаю! Скільки на сьогодні працівників?")
            elif shift == 'night' and current_time == "16:43":
                await bot.send_message(user_id, "🌙 Вітаю! Яка кількість працівників на ніч?")
    except Exception as e:
        logging.error(f"Reminder Error: {e}")

# --- Розділ: Дні народження ---
@dp.message(F.text == "🎂 Дні народження")
async def bday_menu(m: types.Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати", callback_data="e_add")
    kb.button(text="📜 Список", callback_data="e_list")
    kb.button(text="🗑 Видалити", callback_data="e_del_l")
    kb.adjust(2, 1)
    await m.answer("🎂 Керування списком іменинників:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "e_list")
async def e_list(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    # Сортування за календарем (місяць, потім день)
    cur.execute("SELECT full_name, birth_date FROM employees ORDER BY EXTRACT(MONTH FROM birth_date), EXTRACT(DAY FROM birth_date)")
    rows = cur.fetchall(); cur.close(); conn.close()
    
    res = {"Керівники": [], "Працівники": []}
    for name, date in rows:
        line = f"{date.strftime('%d.%m')} — {name}"
        if any(m_name in name for m_name in MANAGERS_NAMES):
            res["Керівники"].append(line)
        else:
            res["Працівники"].append(line)
    
    txt = "📜 **СПИСОК ДН:**\n\n⭐ **КЕРІВНИКИ:**\n" + ("-" if not res["Керівники"] else "\n".join(res["Керівники"]))
    txt += "\n\n👥 **ПРАЦІВНИКИ:**\n" + ("-" if not res["Працівники"] else "\n".join(res["Працівники"]))
    await c.message.answer(txt, parse_mode="Markdown"); await c.answer()

@dp.callback_query(F.data == "e_add")
async def e_add_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть дані: Прізвище Ім'я - ДД.ММ.РРРР\nПриклад: Шевченко Тарас - 09.03.1814")
    await state.set_state(BotStates.waiting_for_employee_data)

@dp.message(BotStates.waiting_for_employee_data)
async def e_add_save(m: types.Message, state: FSMContext):
    try:
        parts = m.text.split(" - ")
        name = parts[0].strip()
        bday = datetime.strptime(parts[1].strip(), "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("INSERT INTO employees (full_name, birth_date) VALUES (%s, %s)", (name, bday))
        conn.commit(); cur.close(); conn.close()
        await m.answer(f"✅ {name} додано до списку!"); await state.clear()
    except:
        await m.answer("❌ Невірний формат. Спробуйте ще раз або натисніть іншу кнопку меню.")

@dp.callback_query(F.data == "e_del_l")
async def e_del_list(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, full_name FROM employees ORDER BY full_name")
    rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for eid, name in rows: kb.button(text=f"🗑 {name}", callback_data=f"ed_{eid}")
    kb.adjust(1)
    await c.message.edit_text("Оберіть кого видалити:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("ed_"))
async def e_del_confirm(c: types.CallbackQuery):
    eid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM employees WHERE id = %s", (eid,)); conn.commit(); cur.close(); conn.close()
    await c.answer("Видалено!"); await e_list(c)

# --- Розділ: Завдання ---
async def tasks_keyboard():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title, is_done FROM tasks ORDER BY id ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for tid, title, done in rows:
        kb.button(text=f"{'✅' if done else '⬜'} {title}", callback_data=f"tgl_{tid}")
    kb.adjust(1).row(types.InlineKeyboardButton(text="➕ Додати завдання", callback_data="t_add"))
    return kb.as_markup()

@dp.message(F.text == "📋 Завдання на зміну")
async def show_tasks(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("Завдання на сьогодні:", reply_markup=await tasks_keyboard())

@dp.callback_query(F.data.startswith("tgl_"))
async def toggle_task(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = %s", (tid,)); conn.commit(); cur.close(); conn.close()
    await c.message.edit_reply_markup(reply_markup=await tasks_keyboard())

@dp.callback_query(F.data == "t_add")
async def t_add_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Напишіть назву завдання:"); await state.set_state(BotStates.waiting_for_task_name)

@dp.message(BotStates.waiting_for_task_name)
async def t_add_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO tasks (title) VALUES (%s)", (m.text,)); conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Завдання додано!"); await state.clear()

# --- Розділ: Маршрути ---
@dp.message(F.text == "🚍 Маршрути")
async def show_routes(m: types.Message, state: FSMContext):
    await state.clear()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT info FROM routes ORDER BY id ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    txt = "🚍 **Маршрути розвозки:**\n\n" + ("Поки порожньо" if not rows else "\n".join([f"📍 {r[0]}" for r in rows]))
    kb = InlineKeyboardBuilder().button(text="➕ Додати маршрут", callback_data="r_add").adjust(1)
    await m.answer(txt, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "r_add")
async def r_add_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть дані (Прізвище - Маршрут):"); await state.set_state(BotStates.waiting_for_route_data)

@dp.message(BotStates.waiting_for_route_data)
async def r_add_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO routes (info) VALUES (%s)", (m.text,)); conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Маршрут збережено!"); await state.clear()

# --- Розділ: Зміна ---
@dp.message(F.text == "⚙️ Зміна")
async def change_shift(m: types.Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder().button(text="☀️ День", callback_data="s_day").button(text="🌙 Ніч", callback_data="s_night").adjust(1)
    await m.answer("Оберіть свою поточну зміну для отримання нагадувань:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("s_"))
async def set_shift(c: types.CallbackQuery):
    shift = "day" if "day" in c.data else "night"
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE users SET shift_type = %s WHERE user_id = %s", (shift, c.from_user.id)); conn.commit(); cur.close(); conn.close()
    await c.message.answer(f"✅ Встановлено графік: {'ДЕНЬ' if shift == 'day' else 'НІЧ'}"); await c.answer()

# --- Системні команди ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    init_db()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (m.from_user.id, m.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await m.answer("👋 Вітаю в робочому боті! Оберіть потрібний розділ:", reply_markup=main_menu())

@dp.message()
async def echo(m: types.Message):
    await m.answer("Будь ласка, використовуйте меню 👇", reply_markup=main_menu())

# --- Запуск додатка ---
async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запуск нагадувань
    scheduler.add_job(check_reminders, "interval", minutes=1)
    scheduler.start()
    
    # Web-сервер для Render
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
