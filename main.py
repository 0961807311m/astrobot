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
        cur.execute("""DO $$ BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='shift_type') THEN
                ALTER TABLE users ADD COLUMN shift_type TEXT DEFAULT 'day';
            END IF;
        END $$;""")
        conn.commit(); cur.close(); conn.close()
    except Exception as e: logging.error(f"DB Error: {e}")

# --- Клавіатури ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Завдання на зміну")
    builder.button(text="🚍 Маршрути")
    builder.button(text="⚙️ Зміна")
    builder.button(text="🎂 Дні народження")
    builder.button(text="💬 Поговорити")
    builder.adjust(1, 1, 2, 1)
    return builder.as_markup(resize_keyboard=True)

# --- Блок Маршрутів ---
@dp.message(F.text == "🚍 Маршрути")
async def show_routes(m: types.Message):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT info FROM routes ORDER BY id ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    text = "🚍 **Маршрути:**\n\n" + ("Порожньо" if not rows else "\n".join([f"📍 {r[0]}" for r in rows]))
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати", callback_data="r_add")
    kb.button(text="🗑 Видалити", callback_data="r_del_list")
    await m.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "r_add")
async def r_add(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Формат: Прізвище - Маршрут - Зупинка"); await state.set_state(BotStates.waiting_for_route_data)

@dp.message(BotStates.waiting_for_route_data)
async def r_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO routes (info) VALUES (%s)", (m.text,)); conn.commit(); cur.close(); conn.close()
    await m.answer("✅ Маршрут додано!"); await state.clear()

@dp.callback_query(F.data == "r_del_list")
async def r_del_l(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, info FROM routes"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder()
    for rid, info in rows: kb.button(text=f"❌ {info[:20]}", callback_data=f"rd_{rid}")
    kb.adjust(1).row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_r"))
    await c.message.edit_text("Видалити маршрут:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("rd_"))
async def r_delete(c: types.CallbackQuery):
    rid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM routes WHERE id = %s", (rid,)); conn.commit(); cur.close(); conn.close()
    await r_del_l(c)

# --- Блок Днів Народження ---
@dp.message(F.text == "🎂 Дні народження")
async def bday_menu(m: types.Message):
    today = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name, role FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
    rows = cur.fetchall(); cur.close(); conn.close()
    text = "Сьогодні іменинників немає." if not rows else "🎉 Сьогодні:\n" + "\n".join([f"🎂 {r[1]}: {r[0]}" for r in rows])
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати", callback_data="e_add")
    kb.button(text="📜 Список", callback_data="e_list")
    kb.button(text="🗑 Видалити", callback_data="e_del_list")
    kb.adjust(2, 1)
    await m.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "e_list")
async def e_list(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name, birth_date, role FROM employees ORDER BY role DESC, to_char(birth_date, 'MM-DD') ASC")
    rows = cur.fetchall(); cur.close(); conn.close()
    res = {"Керівники": [], "Працівники": []}
    for n, d, r in rows: res[r if r in res else "Працівники"].append(f"{d.strftime('%d.%m')} — {n}")
    text = "📜 **Повний список:**\n\n⭐ **КЕРІВНИКИ:**\n" + ("-" if not res["Керівники"] else "\n".join(res["Керівники"]))
    text += "\n\n👥 **ПРАЦІВНИКИ:**\n" + ("-" if not res["Працівники"] else "\n".join(res["Працівники"]))
    await c.message.answer(text, parse_mode="Markdown")
    await c.answer()

@dp.callback_query(F.data == "e_add")
async def e_add(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть: Прізвище Ім'я - ДД.ММ.РРРР"); await state.set_state(BotStates.waiting_for_employee_data)

@dp.message(BotStates.waiting_for_employee_data)
async def e_save_step1(m: types.Message, state: FSMContext):
    try:
        p = m.text.split(" - "); d = datetime.strptime(p[1].strip(), "%d.%m.%Y").date()
        await state.update_data(name=p[0].strip(), bday=p[1].strip())
        kb = InlineKeyboardBuilder()
        kb.button(text="⭐ Керівник", callback_data="role_Керівник")
        kb.button(text="👥 Працівник", callback_data="role_Працівник")
        await m.answer("Оберіть роль:", reply_markup=kb.as_markup())
        await state.set_state(BotStates.waiting_for_employee_role)
    except: await m.answer("❌ Формат: Прізвище Ім'я - ДД.ММ.РРРР")

@dp.callback_query(F.data.startswith("role_"))
async def e_save_step2(c: types.CallbackQuery, state: FSMContext):
    role = c.data.split("_")[1]; data = await state.get_data()
    d = datetime.strptime(data['bday'], "%d.%m.%Y").date()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO employees (full_name, birth_date, role) VALUES (%s, %s, %s)", (data['name'], d, role))
    conn.commit(); cur.close(); conn.close()
    await c.message.edit_text(f"✅ {data['name']} доданий як {role}!"); await state.clear()

# --- Блок Завдань ---
async def tasks_kb():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title, is_done FROM tasks ORDER BY id ASC"); rows = cur.fetchall(); cur.close(); conn.close()
    kb = InlineKeyboardBuilder(); all_done = len(rows) > 0
    for tid, title, done in rows:
        icon = "✅" if done else "⬜"; kb.button(text=f"{icon} {title}", callback_data=f"tgl_{tid}")
        if not done: all_done = False
    kb.adjust(1)
    if all_done and rows: kb.row(types.InlineKeyboardButton(text="🎉 ЗАДАЧІ ВИКОНАНІ! ВДАЛОЇ ЗМІНИ!", callback_data="fin"))
    kb.row(types.InlineKeyboardButton(text="➕ Додати", callback_data="t_add"), types.InlineKeyboardButton(text="🗑 Видалити", callback_data="t_del"))
    return kb.as_markup()

@dp.message(F.text == "📋 Завдання на зміну")
async def show_t(m: types.Message): await m.answer("Завдання:", reply_markup=await tasks_kb())

@dp.callback_query(F.data.startswith("tgl_"))
async def tgl(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1]); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = %s", (tid,)); conn.commit(); cur.close(); conn.close()
    await c.message.edit_reply_markup(reply_markup=await tasks_kb())

@dp.callback_query(F.data == "fin")
async def fin(c: types.CallbackQuery):
    await c.message.answer("🎊 Вдалої зміни!"); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = FALSE"); conn.commit(); cur.close(); conn.close()
    await c.message.edit_reply_markup(reply_markup=await tasks_kb())

# --- Решта функцій (Зміна, ШІ, Запуск) ---
async def check_reminders():
    now = datetime.now()
    if now.weekday() > 5: return
    t = now.strftime("%H:%M")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT user_id, shift_type FROM users"); users = cur.fetchall(); cur.close(); conn.close()
    for uid, shift in users:
        if (shift == 'day' and t == "07:43") or (shift == 'night' and t == "16:43"):
            msg = "Вітаю, скільки на сьогодні працівників?" if shift == 'day' else "Вітаю, яка кількість працівників?"
            try: await bot.send_message(uid, msg)
            except: pass

@dp.message(F.text == "⚙️ Зміна")
async def shift_m(m: types.Message):
    kb = InlineKeyboardBuilder().button(text="☀️ День (07:43)", callback_data="s_day").button(text="🌙 Ніч (16:43)", callback_data="s_night").button(text="🚀 ТЕСТ", callback_data="s_test").adjust(1)
    await m.answer("Графік Пн-Сб:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("s_"))
async def s_set(c: types.CallbackQuery):
    if c.data == "s_test":
        await c.message.answer("Тест: Вітаю, яка кількість працівників?"); return
    s = "day" if "day" in c.data else "night"
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE users SET shift_type = %s WHERE user_id = %s", (s, c.from_user.id)); conn.commit(); cur.close(); conn.close()
    await c.answer(f"Встановлено: {s}")

@dp.message(Command("start"))
async def start(m: types.Message):
    init_db(); conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING", (m.from_user.id, m.from_user.username)); conn.commit(); cur.close(); conn.close()
    await m.answer("🤖 Бот готовий!", reply_markup=main_menu())

@dp.message(F.text)
async def ai(m: types.Message):
    try:
        res = client.chat.completions.create(model="google/gemini-2.0-flash-exp:free", messages=[{"role": "user", "content": m.text}])
        await m.answer(res.choices[0].message.content)
    except: await m.answer("ШІ зайнятий.")

async def main():
    init_db(); await bot.delete_webhook(drop_pending_updates=True)
    scheduler.add_job(check_reminders, "interval", minutes=1); scheduler.start()
    app = web.Application(); app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
