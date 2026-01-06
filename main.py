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
    waiting_for_route_data = State() # Новий стан для маршрутів

# --- База даних ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, shift_type TEXT DEFAULT 'day');")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE);")
        cur.execute("CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT, is_done BOOLEAN DEFAULT FALSE);")
        # Нова таблиця для маршрутів
        cur.execute("CREATE TABLE IF NOT EXISTS routes (id SERIAL PRIMARY KEY, info TEXT);")
        
        # Перевірка наявності колонки shift_type
        cur.execute("""
            DO $$ BEGIN 
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='shift_type') THEN
                    ALTER TABLE users ADD COLUMN shift_type TEXT DEFAULT 'day';
                END IF;
            END $$;
        """)
        
        conn.commit()
        cur.close(); conn.close()
        logging.info("✅ БД готова")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# --- Меню та клавіатури ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Завдання на зміну")
    builder.button(text="🚍 Маршрути")
    builder.button(text="⚙️ Зміна")
    builder.button(text="🎂 Дні народження")
    builder.button(text="💬 Поговорити")
    builder.adjust(1, 1, 2, 1)
    return builder.as_markup(resize_keyboard=True)

async def routes_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати маршрут", callback_data="route_add")
    builder.button(text="🗑 Видалити маршрут", callback_data="route_list_del")
    builder.adjust(1)
    return builder.as_markup()

# --- Хендлери Маршрутів ---
@dp.message(F.text == "🚍 Маршрути")
async def show_routes(message: types.Message):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT info FROM routes ORDER BY id ASC")
    rows = cur.fetchall(); cur.close(); conn.close()
    
    if not rows:
        text = "Список маршрутів поки порожній."
    else:
        text = "🚍 **Список маршрутів:**\n\n" + "\n".join([f"📍 {r[0]}" for r in rows])
    
    await message.answer(text, reply_markup=await routes_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "route_add")
async def route_add_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Пришліть дані у форматі:\n**Прізвище - Маршрут - Зупинка**")
    await state.set_state(BotStates.waiting_for_route_data)
    await callback.answer()

@dp.message(BotStates.waiting_for_route_data)
async def route_save(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO routes (info) VALUES (%s)", (message.text,))
    conn.commit(); cur.close(); conn.close()
    await message.answer(f"✅ Маршрут збережено!", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data == "route_list_del")
async def route_del_list(callback: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT id, info FROM routes"); rows = cur.fetchall(); cur.close(); conn.close()
    builder = InlineKeyboardBuilder()
    for rid, info in rows:
        builder.button(text=f"❌ {info[:30]}...", callback_data=f"rdel_{rid}")
    builder.adjust(1)
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_routes"))
    await callback.message.edit_text("Оберіть маршрут для видалення:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("rdel_"))
async def route_delete(callback: types.CallbackQuery):
    rid = int(callback.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("DELETE FROM routes WHERE id = %s", (rid,))
    conn.commit(); cur.close(); conn.close()
    await route_del_list(callback)

@dp.callback_query(F.data == "back_to_routes")
async def back_to_routes_call(callback: types.CallbackQuery):
    await show_routes(callback.message)
    await callback.answer()

# --- Решта функцій (Завдання, Зміна, ШІ) ---
# [Залишаємо без змін з попереднього робочого коду]

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    init_db()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (m.from_user.id, m.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await m.answer("🚀 Бот запущений!", reply_markup=main_menu())

@dp.message(F.text == "📋 Завдання на зміну")
async def show_t(message: types.Message):
    # Використовуємо функцію tasks_kb з попередньої відповіді
    from main import tasks_kb # якщо функції в одному файлі, просто викликаємо
    await message.answer("Завдання:", reply_markup=await tasks_kb())

# [Тут додайте всі інші хендлери для задач, змін та дн з попередньої версії]
# Для економії місця я наводжу лише структуру запуску

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2)
    
    # scheduler...
    # web app...
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
