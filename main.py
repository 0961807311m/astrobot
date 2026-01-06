import os
import asyncio
import logging
import psycopg2
import io
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

# --- Конфігурація ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("OPENROUTER_API_KEY") 
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY, max_retries=0)

class BotStates(StatesGroup):
    waiting_for_employee_data = State()
    waiting_for_task_name = State()

# --- База даних ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT);")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE);")
        cur.execute("CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT, is_done BOOLEAN DEFAULT FALSE);")
        conn.commit()
        cur.close(); conn.close()
        logging.info("✅ БД готова (задачі додано)")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# --- Робота з ШІ ---
async def ask_ai(system_prompt, user_prompt):
    models = ["google/gemini-2.0-flash-exp:free", "meta-llama/llama-3.1-8b-instruct:free", "qwen/qwen-2.5-72b-instruct:free"]
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                extra_headers={"HTTP-Referer": "https://render.com", "X-Title": "AstroBot_vFinal"},
                timeout=12.0 
            )
            return response.choices[0].message.content
        except: continue 
    return "⚠️ ШІ перевантажений."

# --- Клавіатури ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Завдання на зміну")
    builder.button(text="🎂 Дні народження")
    builder.button(text="💬 Поговорити")
    builder.adjust(1, 2)
    return builder.as_markup(resize_keyboard=True)

async def tasks_keyboard():
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title, is_done FROM tasks ORDER BY id ASC")
    tasks = cur.fetchall(); cur.close(); conn.close()
    
    builder = InlineKeyboardBuilder()
    all_done = True
    for tid, title, is_done in tasks:
        icon = "✅" if is_done else "⬜"
        if not is_done: all_done = False
        builder.button(text=f"{icon} {title}", callback_data=f"toggle_{tid}")
    
    builder.adjust(1)
    
    # Якщо всі задачі виконані, додаємо фінальну кнопку
    if all_done and tasks:
        builder.row(types.InlineKeyboardButton(text="🎉 Усі задачі виконано! Вдалої зміни!", callback_data="finish_shift"))
    
    # Кнопки керування
    builder.row(
        types.InlineKeyboardButton(text="➕ Додати задачу", callback_data="add_task"),
        types.InlineKeyboardButton(text="🗑 Видалити/Ред", callback_data="edit_tasks_list")
    )
    return builder.as_markup()

# --- Хендлери Завдань ---

@dp.message(F.text == "📋 Завдання на зміну")
async def show_tasks(message: types.Message):
    await message.answer("📝 Список завдань на сьогодні:", reply_markup=await tasks_keyboard())

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_task(callback: types.CallbackQuery):
    tid = int(callback.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = %s", (tid,))
    conn.commit(); cur.close(); conn.close()
    await callback.message.edit_reply_markup(reply_markup=await tasks_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "add_task")
async def add_task_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть назву нової задачі:")
    await state.set_state(BotStates.waiting_for_task_name)
    await callback.answer()

@dp.message(BotStates.waiting_for_task_name)
async def save_task(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO tasks (title) VALUES (%s)", (message.text,))
    conn.commit(); cur.close(); conn.close()
    await message.answer(f"✅ Задача '{message.text}' додана!", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data == "edit_tasks_list")
async def edit_tasks_view(callback: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, title FROM tasks")
    tasks = cur.fetchall(); cur.close(); conn.close()
    builder = InlineKeyboardBuilder()
    for tid, title in tasks:
        builder.button(text=f"❌ Видалити: {title}", callback_data=f"del_task_{tid}")
    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_tasks"))
    await callback.message.edit_text("Оберіть задачу для видалення:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("del_task_"))
async def delete_task(callback: types.CallbackQuery):
    tid = int(callback.data.split("_")[3])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (tid,))
    conn.commit(); cur.close(); conn.close()
    await callback.answer("Видалено")
    await edit_tasks_view(callback)

@dp.callback_query(F.data == "back_to_tasks")
async def back_to_tasks(callback: types.CallbackQuery):
    await callback.message.edit_text("📝 Список завдань на сьогодні:", reply_markup=await tasks_keyboard())

@dp.callback_query(F.data == "finish_shift")
async def finish_shift_call(callback: types.CallbackQuery):
    await callback.message.answer("🎊 Чудова робота! Бажаємо гарного відпочинку!")
    # Скидаємо статус задач для наступної зміни
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = FALSE")
    conn.commit(); cur.close(); conn.close()
    await callback.answer()

# --- Решта функцій (Дні народження, Чат) ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    await message.answer("🚀 Бот оновлений! Оберіть розділ:", reply_markup=main_menu())

@dp.message(F.text == "🎂 Дні народження")
async def bdays_menu(message: types.Message):
    today = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
    workers = cur.fetchall(); cur.close(); conn.close()
    text = "Сьогодні іменинників немає. ✨" if not workers else "🎉 Сьогодні святкують:\n" + "\n".join([f"🎂 {w[0]}" for w in workers])
    
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати", callback_data="add_employee")
    kb.button(text="📥 Скачати", callback_data="download_employees")
    await message.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "add_employee")
async def start_add_emp(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Формат: Прізвище Ім'я - ДД.ММ.РРРР")
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
    except: await message.answer("❌ Помилка формату!")

@dp.message(F.text == "💬 Поговорити")
async def talk(message: types.Message):
    await message.answer("Я слухаю. Напиши своє запитання!")

@dp.message(F.text)
async def chat(message: types.Message):
    await bot.send_chat_action(message.chat.id, "typing")
    ans = await ask_ai("Ти корисний помічник.", message.text)
    await message.answer(ans)

# --- Запуск ---
async def main():
    init_db()
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    scheduler.start()
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
