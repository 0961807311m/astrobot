import os
import asyncio
import logging
import psycopg2
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
client = OpenAI(base_url="https://api.groq.com/openai/v1" if "gsk" in (API_KEY or "") else "https://openrouter.ai/api/v1", api_key=API_KEY)

class UserProfile(StatesGroup):
    waiting_for_birthday = State()

# --- База даних ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, birthday DATE);")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday DATE;")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE);")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# --- Робота з ШІ (Мульти-модельний підхід) ---
async def ask_ai(system_prompt, user_prompt):
    models = [
        "google/gemini-2.0-flash-exp:free", 
        "meta-llama/llama-3.3-70b-versatile", # Якщо використовуєте Groq
        "meta-llama/llama-3.2-3b-instruct:free",
        "openrouter/auto-free"
    ]
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                extra_headers={"HTTP-Referer": "https://render.com", "X-Title": "AstroBot"}
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.warning(f"⚠️ Модель {model} не відповіла: {e}")
            continue
    return "⚠️ Вибачте, ШІ тимчасово недоступний."

# --- Функція автоматичного привітання ---
async def daily_birthday_check():
    logging.info("⏰ Запуск щоденної перевірки іменинників...")
    today = datetime.now().strftime("%m-%d")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Шукаємо іменинників
        cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
        workers = cur.fetchall()
        
        if workers:
            # Отримуємо список усіх користувачів бота, щоб розіслати привітання
            cur.execute("SELECT user_id FROM users")
            users = cur.fetchall()
            
            text = "🎉 **Сьогоднішні іменинники!**\n\n" + "\n".join([f"🎂 {w[0]}" for w in workers]) + "\n\nНе забудьте привітати колег! ✨"
            
            for user in users:
                try:
                    await bot.send_message(user[0], text, parse_mode="Markdown")
                    await asyncio.sleep(0.05) # Захист від спам-фільтру Telegram
                except Exception:
                    continue
        
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Помилка привітання: {e}")

# --- Меню та Хендлери ---
def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💬 Поговорити")
    builder.button(text="✨ Порада дня")
    builder.button(text="🎂 Дні народження")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    # Додаємо користувача в базу, щоб він отримував розсилку
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", (message.from_user.id, message.from_user.username))
    conn.commit(); cur.close(); conn.close()
    
    await message.answer(f"Привіт, {message.from_user.first_name}! 🚀 Я готовий до роботи.", reply_markup=main_menu_kb())

@dp.message(F.text == "💬 Поговорити")
async def talk_mode(message: types.Message):
    await message.answer("Слухаю тебе! Напиши мені що завгодно.")

@dp.message(F.text == "✨ Порада дня")
async def astro_advice(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT birthday FROM users WHERE user_id = %s", (message.from_user.id,))
    res = cur.fetchone(); cur.close(); conn.close()

    if not res or not res[0]:
        await message.answer("Введіть дату народження (ДД.ММ.РРРР):")
        await state.set_state(UserProfile.waiting_for_birthday)
    else:
        await bot.send_chat_action(message.chat.id, "typing")
        advice = await ask_ai("Ти коуч. Дай пораду на день за Матрицею Долі.", f"Дата: {res[0]}. Дай пораду, очікування, уникання та бали енергії.")
        await message.answer(advice)

@dp.message(UserProfile.waiting_for_birthday)
async def process_bday(message: types.Message, state: FSMContext):
    try:
        bday = datetime.strptime(message.text, "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("UPDATE users SET birthday = %s WHERE user_id = %s", (bday, message.from_user.id))
        conn.commit(); cur.close(); conn.close()
        await message.answer("✅ Готово! Тисни 'Порада дня'.", reply_markup=main_menu_kb())
        await state.clear()
    except:
        await message.answer("❌ Формат: ДД.ММ.РРРР")

@dp.message(F.text == "🎂 Дні народження")
async def check_now(message: types.Message):
    await daily_birthday_check() # Викликаємо ту ж саму функцію

# --- Запуск ---
async def main():
    init_db()
    
    # Налаштування планувальника
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    # Додаємо завдання: щодня о 09:00
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
