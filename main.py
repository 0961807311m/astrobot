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

# --- Конфигурация ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("OPENROUTER_API_KEY") 
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY, max_retries=0)

class BotStates(StatesGroup):
    waiting_for_user_birthday = State()
    waiting_for_employee_data = State()

# --- База данных ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, birthday DATE);")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE);")
        conn.commit()
        cur.close(); conn.close()
        logging.info("✅ БД готова")
    except Exception as e:
        logging.error(f"❌ Ошибка БД: {e}")

# --- Работа с ИИ ---
async def ask_ai(system_prompt, user_prompt):
    models = [
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "gryphe/mythomax-l2-13b:free"
    ]
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                extra_headers={"HTTP-Referer": "https://render.com", "X-Title": "AstroBot_vFinal"},
                timeout=12.0 
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.warning(f"⚠️ {model} ошибка. Пробую следующую...")
            await asyncio.sleep(0.7)
            continue 
    return "⚠️ Линии ИИ перегружены. Попробуйте позже."

# --- Рассылка поздравлений ---
async def daily_birthday_check():
    today = datetime.now().strftime("%m-%d")
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
        workers = cur.fetchall()
        if workers:
            cur.execute("SELECT user_id FROM users")
            all_users = cur.fetchall()
            names = ", ".join([w[0] for w in workers])
            text = f"🎉 **Сегодня день рождения празднуют:**\n\n🎂 {names}\n\nНе забудьте поздравить коллег! ✨"
            for user in all_users:
                try: await bot.send_message(user[0], text, parse_mode="Markdown")
                except: continue
        cur.close(); conn.close()
    except Exception as e: logging.error(f"❌ Ошибка планировщика: {e}")

# --- Клавиатуры ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💬 Поговорить")
    builder.button(text="✨ Совет дня")
    builder.button(text="🎂 Дни рождения")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

def employees_inline():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить", callback_data="add_employee")
    builder.button(text="📥 Скачать список", callback_data="download_employees")
    builder.adjust(2)
    return builder.as_markup()

# --- Хендлеры ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (message.from_user.id, message.from_user.username))
    conn.commit(); cur.close(); conn.close()
    await message.answer("🚀 Бот запущен! Выберите раздел:", reply_markup=main_menu())

@dp.message(F.text == "🎂 Дни рождения")
async def bdays_menu(message: types.Message):
    today = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
    workers = cur.fetchall(); cur.close(); conn.close()
    text = "Сегодня именинников нет. ✨" if not workers else "🎉 Сегодня празднуют:\n" + "\n".join([f"🎂 {w[0]}" for w in workers])
    await message.answer(text, reply_markup=employees_inline())

@dp.callback_query(F.data == "download_employees")
async def download_employees(callback: types.CallbackQuery):
    try:
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("SELECT full_name, birth_date FROM employees ORDER BY to_char(birth_date, 'MM-DD') ASC")
        workers = cur.fetchall(); cur.close(); conn.close()
        if not workers:
            await callback.answer("Список пуст!", show_alert=True)
            return
        
        output = "СПИСОК СОТРУДНИКОВ\n" + "="*25 + "\n"
        for name, bday in workers:
            output += f"{bday.strftime('%d.%m.%Y')} — {name}\n"
        
        file_data = BufferedInputFile(output.encode('utf-8'), filename="employees.txt")
        await callback.message.answer_document(file_data, caption="📂 Полный список именинников.")
        await callback.answer()
    except Exception as e:
        await callback.answer("Ошибка при скачивании.")

@dp.callback_query(F.data == "add_employee")
async def start_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Пришлите данные в формате: **Имя Фамилия - ДД.ММ.ГГГГ**")
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
        await message.answer(f"✅ {name} добавлен!", reply_markup=main_menu())
        await state.clear()
    except: await message.answer("❌ Ошибка! Формат: Имя - ДД.ММ.ГГГГ")

@dp.message(F.text == "✨ Совет дня")
async def astro_handler(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT birthday FROM users WHERE user_id = %s", (message.from_user.id,))
    res = cur.fetchone(); cur.close(); conn.close()
    if not res or not res[0]:
        await message.answer("Введите вашу дату рождения (ДД.ММ.ГГГГ):")
        await state.set_state(BotStates.waiting_for_user_birthday)
    else:
        await bot.send_chat_action(message.chat.id, "typing")
        ans = await ask_ai("Ти коуч. Дай пораду дня українською.", f"Дата: {res[0].strftime('%d.%m.%Y')}.")
        await message.answer(ans)

@dp.message(BotStates.waiting_for_user_birthday)
async def set_user_bday(message: types.Message, state: FSMContext):
    try:
        bday = datetime.strptime(message.text, "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("UPDATE users SET birthday = %s WHERE user_id = %s", (bday, message.from_user.id))
        conn.commit(); cur.close(); conn.close()
        await message.answer("✅ Сохранено! Нажмите кнопку еще раз.")
        await state.clear()
    except: await message.answer("❌ Формат: ДД.ММ.ГГГГ")

@dp.message(F.text == "💬 Поговорить")
async def talk(message: types.Message):
    await message.answer("Я слушаю! О чем хочешь спросить?")

@dp.message(F.text)
async def chat(message: types.Message):
    await bot.send_chat_action(message.chat.id, "typing")
    ans = await ask_ai("Ты полезный ИИ-помощник.", message.text)
    await message.answer(ans)

async def main():
    init_db()
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    scheduler.add_job(daily_birthday_check, "cron", hour=9, minute=0)
    scheduler.start()
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
