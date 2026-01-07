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

# --- Налаштування логування ---
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

# --- База даних та виправлення ролей ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT);")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE, role TEXT DEFAULT 'Працівник');")
        cur.execute("CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT, is_done BOOLEAN DEFAULT FALSE);")
        cur.execute("CREATE TABLE IF NOT EXISTS routes (id SERIAL PRIMARY KEY, info TEXT);")
        
        cur.execute("""DO $$ BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='shift_type') THEN
                ALTER TABLE users ADD COLUMN shift_type TEXT DEFAULT 'day';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='employees' AND column_name='role') THEN
                ALTER TABLE employees ADD COLUMN role TEXT DEFAULT 'Працівник';
            END IF;
        END $$;""")
        conn.commit(); cur.close(); conn.close()
    except Exception as e: logging.error(f"❌ DB Error: {e}")

def fix_manager_roles():
    """Автоматично переносить вказаних людей у розділ Керівники"""
    managers = [
        "Костюк Леся", "Склярук Анатолій", "Квартюк Іван", "Коваль Мирослава", "Селіверстов Олег", 
        "Хоха", "Полігас Андрій", "Козак Олег", "Лиховид Сергій Миколайович", "Маснюк Олександр", 
        "Москаленко Вова", "Людяний Олександр", "Лиховид Юра", "Кравець Михайло", "Влага Анатолій", 
        "Рутковська Діана", "Манченко Сергій", "Кушнір Андрій", "Склярук Тетяна", "Островий Сергій", 
        "Семеніхін Олексій", "Кравченко Ігор", "Бойко Тетяна", "Влага Ганна"
    ]
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        for name in managers:
            cur.execute("UPDATE employees SET role = 'Керівник' WHERE full_name = %s", (name,))
        conn.commit(); cur.close(); conn.close()
        logging.info("✅ Ролі керівників виправлено")
    except Exception as e: logging.error(f"Migration error: {e}")

# --- Меню ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Завдання на зміну")
    builder.button(text="🚍 Маршрути")
    builder.button(text="⚙️ Зміна")
    builder.button(text="🎂 Дні народження")
    builder.adjust(1, 1, 2)
    return builder.as_markup(resize_keyboard=True)

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
                msg = "Вітаю, скільки на сьогодні працівників?" if shift == 'day' else "Вітаю, яка кількість працівників?"
                try: await bot.send_message(uid, msg)
                except: pass
    except Exception as e: logging.error(f"Reminder error: {e}")

# --- Дні Народження (ВИПРАВЛЕНО сортування) ---
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
    # Сортування: Спочатку Керівники, потім Працівники. Всередині груп - за місяцем і днем (січень-грудень)
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

# --- Хендлери для Маршрутів ---
@dp.message(F.text == "🚍 Маршрути")
async def show_routes(m: types.Message):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT info FROM routes ORDER BY id ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    text = "🚍 **Маршрути:**\n\n" + ("Порожньо" if not rows else "\n".join([f"📍 {r[0]}" for r in rows]))
    kb = InlineKeyboardBuilder().button(text="➕ Додати", callback_data="r_add").button(text="🗑 Видалити", callback_data="r_del_list").adjust(2)
    await m.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "r_add")
async def r_add(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Пришліть: Прізвище - Маршрут - Зупинка"); await state.set_state(BotStates.waiting_for_route_data)

@dp.message(BotStates.waiting_for_route_data)
async def r_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO routes (info) VALUES (%s)", (m.text,)); conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Маршрут збережено!"); await state.clear()

@dp.callback_query(F.data == "r_del_list")
async def r_del_l(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, info FROM routes"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for rid, info in rows: kb.button(text=f"❌ {info[:20]}...", callback_data=f"rdel_{rid}")
    kb.adjust(1).row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_r"))
    await c.message.edit_text("Видалити маршрут:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("rdel_"))
async def r_delete(c: types.CallbackQuery):
    rid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM routes WHERE id = %s", (rid,)); conn.commit(); cur.close(); conn.close()
    await r_del_l(c)

@dp.callback_query(F.data == "back_r")
async def back_r(c: types.CallbackQuery): await show_routes(c.message)

# --- Завдання ---
async def t_kb():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title, is_done FROM tasks ORDER BY id ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder(); all_d = len(rows) > 0
    for tid, title, done in rows:
        icon = "✅" if done else "⬜"; kb.button(text=f"{icon} {title}", callback_data=f"tgl_{tid}")
        if not done: all_d = False
    kb.adjust(1)
    if all_d and rows: kb.row(types.InlineKeyboardButton(text="🎉 ЗАДАЧІ ВИКОНАНІ!", callback_data="t_fin"))
    kb.row(types.InlineKeyboardButton(text="➕ Додати", callback_data="t_add"), types.InlineKeyboardButton(text="🗑 Видалити", callback_data="t_del_l"))
    return kb.as_markup()

@dp.message(F.text == "📋 Завдання на зміну")
async def show_t(m: types.Message): await m.answer("Список завдань:", reply_markup=await t_kb())

@dp.callback_query(F.data.startswith("tgl_"))
async def tgl(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = %s", (tid,)); conn.commit(); cur.close(); conn.close()
    await c.message.edit_reply_markup(reply_markup=await t_kb())

@dp.callback_query(F.data == "t_add")
async def t_add(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Назва завдання:"); await state.set_state(BotStates.waiting_for_task_name)

@dp.message(BotStates.waiting_for_task_name)
async def t_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO tasks (title) VALUES (%s)", (m.text,)); conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Додано!"); await state.clear()

@dp.callback_query(F.data == "t_del_l")
async def t_del_l(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title FROM tasks"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for tid, title in rows: kb.button(text=f"🗑 {title}", callback_data=f"tdel_{tid}")
    kb.adjust(1).row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_t"))
    await c.message.edit_text("Видалити завдання:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("tdel_"))
async def t_del_do(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (tid,)); conn.commit(); cur.close(); conn.close()
    await t_del_l(c)

@dp.callback_query(F.data == "back_t")
async def back_t(c: types.CallbackQuery): await c.message.edit_text("Список завдань:", reply_markup=await t_kb())

# --- Налаштування ДН ---
@dp.callback_query(F.data == "e_add")
async def e_add(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Прізвище Ім'я - ДД.ММ.РРРР"); await state.set_state(BotStates.waiting_for_employee_data)

@dp.message(BotStates.waiting_for_employee_data)
async def e_save1(m: types.Message, state: FSMContext):
    try:
        p = m.text.split(" - "); datetime.strptime(p[1].strip(), "%d.%m.%Y")
        await state.update_data(name=p[0].strip(), bday=p[1].strip())
        kb = InlineKeyboardBuilder().button(text="⭐ Керівник", callback_data="erole_Керівник").button(text="👥 Працівник", callback_data="erole_Працівник")
        await m.answer("Оберіть категорію:", reply_markup=kb.as_markup()); await state.set_state(BotStates.waiting_for_employee_role)
    except: await m.answer("❌ Формат: Прізвище Ім'я - 01.01.1990")

@dp.callback_query(F.data.startswith("erole_"))
async def e_save2(c: types.CallbackQuery, state: FSMContext):
    role = c.data.split("_")[1]; data = await state.get_data(); d = datetime.strptime(data['bday'], "%d.%m.%Y").date()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO employees (full_name, birth_date, role) VALUES (%s, %s, %s)", (data['name'], d, role))
    conn.commit(); cur.close(); conn.close()
    await c.message.edit_text(f"✅ {data['name']} доданий!"); await state.clear()

@dp.callback_query(F.data == "e_del_l")
async def e_del_l(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, full_name FROM employees ORDER BY full_name ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for eid, name in rows: kb.button(text=f"🗑 {name}", callback_data=f"ed_{eid}")
    kb.adjust(1).row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_bday"))
    await c.message.edit_text("Видалити працівника:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("ed_"))
async def e_del_do(c: types.CallbackQuery):
    eid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM employees WHERE id = %s", (eid,)); conn.commit(); cur.close(); conn.close()
    await e_del_l(c)

@dp.callback_query(F.data == "back_bday")
async def back_b(c: types.CallbackQuery): await bday_m(c.message)

# --- Зміна та Старт ---
@dp.message(F.text == "⚙️ Зміна")
async def shift_m(m: types.Message):
    kb = InlineKeyboardBuilder().button(text="☀️ День", callback_data="s_day").button(text="🌙 Ніч", callback_data="s_night").adjust(1)
    await m.answer("Оберіть зміну:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("s_"))
async def s_set(c: types.CallbackQuery):
    s = "day" if "day" in c.data else "night"
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE users SET shift_type = %s WHERE user_id = %s", (s, c.from_user.id)); conn.commit(); cur.close(); conn.close()
    await c.answer(f"Встановлено: {s}")

@dp.message(Command("start"))
async def start(m: types.Message):
    init_db()
    fix_manager_roles() # ВИПРАВЛЯЄМО РОЛІ ПРИ ЗАПУСКУ
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", (m.from_user.id, m.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await m.answer("👋 Бот готовий! Список Керівників виправлено.", reply_markup=main_menu())

@dp.message()
async def any_text(m: types.Message):
    await m.answer("Скористайтеся кнопками меню 👇", reply_markup=main_menu())

# --- Запуск ---
async def main():
    init_db(); await bot.delete_webhook(drop_pending_updates=True)
    scheduler.add_job(reminders, "interval", minutes=1); scheduler.start()
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
