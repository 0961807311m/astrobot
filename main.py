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
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

class BotStates(StatesGroup):
    waiting_for_employee_data = State()
    waiting_for_employee_role = State()
    waiting_for_task_name = State()
    waiting_for_route_data = State()

# --- База даних ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, shift_type TEXT DEFAULT 'day');")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE, role TEXT DEFAULT 'Працівник');")
        cur.execute("CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT, is_done BOOLEAN DEFAULT FALSE);")
        cur.execute("CREATE TABLE IF NOT EXISTS routes (id SERIAL PRIMARY KEY, info TEXT);")
        conn.commit(); cur.close(); conn.close()
    except Exception as e: logging.error(f"❌ DB Error: {e}")

# Функція для автоматичного перенесення керівників
def migrate_managers_logic():
    managers_list = [
        "Костюк Леся", "Склярук Анатолій", "Квартюк Іван", "Коваль Мирослава", "Селіверстов Олег",
        "Хоха", "Полігас Андрій", "Козак Олег", "Лиховид Сергій Миколайович", "Маснюк Олександр",
        "Москаленко Вова", "Людяний Олександр", "Лиховид Юра", "Кравець Михайло", "Влага Анатолій",
        "Рутковська Діана", "Манченко Сергій", "Кушнір Андрій", "Склярук Тетяна", "Островий Сергій",
        "Семеніхін Олексій", "Кравченко Ігор", "Бойко Тетяна", "Влага Ганна"
    ]
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        for name in managers_list:
            cur.execute("UPDATE employees SET role = 'Керівник' WHERE full_name = %s", (name,))
        conn.commit(); cur.close(); conn.close()
        logging.info("✅ Ролі керівників оновлено!")
    except Exception as e: logging.error(f"Migration error: {e}")

def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Завдання на зміну")
    builder.button(text="🚍 Маршрути")
    builder.button(text="⚙️ Зміна")
    builder.button(text="🎂 Дні народження")
    builder.adjust(1, 1, 2)
    return builder.as_markup(resize_keyboard=True)

# --- Дні Народження (З правильним сортуванням) ---
@dp.message(F.text == "🎂 Дні народження")
async def bday_m(m: types.Message):
    t = datetime.now().strftime("%m-%d"); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name, role FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (t,))
    rows = cur.fetchall(); cur.close(); conn.close()
    msg = "Сьогодні іменинників немає." if not rows else "🎉 Сьогодні:\n" + "\n".join([f"🎂 {r[1]}: {r[0]}" for r in rows])
    kb = InlineKeyboardBuilder().button(text="➕ Додати", callback_data="e_add").button(text="📜 Список", callback_data="e_list").button(text="🗑 Видалити", callback_data="e_del_l").adjust(2, 1)
    await m.answer(msg, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "e_list")
async def e_list(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    # Сортування: 1. Керівники вище. 2. За місяцем. 3. За днем.
    cur.execute("""
        SELECT full_name, birth_date, role FROM employees 
        ORDER BY CASE WHEN role='Керівник' THEN 1 ELSE 2 END, 
        EXTRACT(MONTH FROM birth_date) ASC, 
        EXTRACT(DAY FROM birth_date) ASC
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    res = {"Керівники": [], "Працівники": []}
    for n, d, r in rows:
        res[r if r in res else "Працівники"].append(f"{d.strftime('%d.%m')} — {n}")
    
    txt = "📜 **СПИСОК:**\n\n⭐ **КЕРІВНИКИ:**\n" + ("-" if not res["Керівники"] else "\n".join(res["Керівники"]))
    txt += "\n\n👥 **ПРАЦІВНИКИ:**\n" + ("-" if not res["Працівники"] else "\n".join(res["Працівники"]))
    await c.message.answer(txt, parse_mode="Markdown"); await c.answer()

# --- Хендлери для Маршрутів, Задач та Змін залишаються без змін ---
# (Додайте їх сюди з попереднього коду)

# --- Нагадування ---
async def reminders():
    now = datetime.now()
    if now.weekday() > 5: return 
    t = now.strftime("%H:%M")
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("SELECT user_id, shift_type FROM users"); users = cur.fetchall(); cur.close(); conn.close()
        for uid, shift in users:
            if (shift == 'day' and t == "07:43") or (shift == 'night' and t == "16:43"):
                msg = "Вітаю, скільки на сьогодні працівників?"
                try: await bot.send_message(uid, msg)
                except: pass
    except: pass

@dp.message(Command("start"))
async def start(m: types.Message):
    init_db()
    migrate_managers_logic() # Авто-виправлення ролей
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", (m.from_user.id, m.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await m.answer("👋 Бот налаштований! Керівників перенесено, список впорядковано.", reply_markup=main_menu())

@dp.message()
async def echo(m: types.Message):
    await m.answer("Скористайтеся меню 👇", reply_markup=main_menu())

async def main():
    init_db(); await bot.delete_webhook(drop_pending_updates=True)
    scheduler.add_job(reminders, "interval", minutes=1); scheduler.start()
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
