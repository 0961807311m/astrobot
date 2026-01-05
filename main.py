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

# --- Конфігурація логування ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("OPENROUTER_API_KEY") 
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY)

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
        logging.info("✅ База даних ініціалізована та перевірена")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# --- Робота з ШІ (Мульти-модельний Fallback) ---
async def ask_ai(system_prompt, user_prompt):
    # Список безкоштовних актуальних моделей для обходу Rate Limits (429)
    models = [
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free"
    ]
    
    for model in models:
        try:
            logging.info(f"🤖 Спроба моделі: {model}")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                extra_headers={"HTTP-Referer": "https://render.com", "X-Title": "AstroBotV3"},
                timeout=20.0
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.warning(f"⚠️ Модель {model} не відповіла: {str(e)[:50]}")
            continue # Пробуємо наступну
            
    return "⚠️ На жаль, усі лінії ШІ зараз перевантажені. Спробуйте надіслати запит ще раз через 15 секунд."

# --- Функція автоматичного привітання о 09:00 ---
async def daily_birthday_check():
    today = datetime.now().strftime("%m-%d")
    logging.info(f"⏰ Запуск перевірки іменинників: {today}")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
        workers = cur.fetchall()
        
        if workers:
            cur.execute("SELECT user_id FROM users")
            all_users = cur.fetchall()
            names = ", ".join([w[0] for w in workers])
            text = f"🎉 **Сьогодні святкують день народження:**\n\n🎂 {names}\n\nНе забудьте привітати колег! ✨"
            
            for user in all_users:
                try:
                    await bot.send_message(user[0], text, parse_mode="Markdown")
                    await asyncio.sleep(0.05)
                except: continue
        cur.close(); conn.close()
    except Exception as e:
        logging.error(f"❌ Помилка в daily_birthday_check: {e}")

# --- Кнопки ---
def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💬 Поговорити")
    builder.button(text="✨ Порада дня")
    builder.button(text="🎂 Дні народження")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

# --- Хендлери ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    # Реєструємо користувача для розсилки привітань
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", 
                (message.from_user.id, message.from_user.username))
    conn.commit(); cur.close(); conn.close()
    
    await message.answer(
        f"Привіт, {message.from_user.first_name}! 🚀\nЯ твій персональний ШІ-асистент. Оберіть дію:",
        reply_markup=main_menu_kb()
    )

@dp.message(F.text == "💬 Поговорити")
async def talk_mode(message: types.Message):
    await message.answer("Я уважно слухаю. Про що хочеш поспілкуватися?")

@dp.message(F.text == "✨ Порада дня")
async def astro_advice(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT birthday FROM users WHERE user_id = %s", (message.from_user.id,))
    res = cur.fetchone(); cur.close(); conn.close()

    if not res or not res[0]:
        await message.answer("Введіть дату народження у форматі: **ДД.ММ.РРРР**\n(Наприклад: 15.08.1990)")
        await state.set_state(UserProfile.waiting_for_birthday)
    else:
        await bot.send_chat_action(message.chat.id, "typing")
        sys_p = "Ти коуч з саморозвитку. Дай пораду на день за Матрицею Долі. Пиши: 1. Порада. 2. Чого очікувати. 3. Чого уникати. 4. Енергія дня (бали 0-100). Українською."
        usr_p = f"Моя дата: {res[0].strftime('%d.%m.%Y')}. Сьогодні: {datetime.now().strftime('%d.%m.%Y')}."
        advice = await ask_ai(sys_p, usr_p)
        await message.answer(f"🔮 **Твій прогноз:**\n\n{advice}")

@dp.message(UserProfile.waiting_for_birthday)
async def process_bday(message: types.Message, state: FSMContext):
    try:
        bday = datetime.strptime(message.text, "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("UPDATE users SET birthday = %s WHERE user_id = %s", (bday, message.from_user.id))
        conn.commit(); cur.close(); conn.close()
        await message.answer("✅ Дату збережено! Натисніть '✨ Порада дня' ще раз.", reply_markup=main_menu_kb())
        await state.clear()
    except:
        await message.answer("❌ Невірний формат. Спробуйте ДД.ММ.РРРР (наприклад 01.01.2000)")

@dp.message(F.text == "🎂 Дні народження")
async def check_bdays(message: types.Message):
    today = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
    workers = cur.fetchall(); cur.close(); conn.close()
    if workers:
        await message.answer("🎉 Сьогодні святкують:\n" + "\n".join([f"🎂 {w[0]}" for w in workers]))
    else:
        await message.answer("Сьогодні іменинників серед працівників немає. ✨")

# Обробка будь-якого іншого тексту (чат з ШІ)
@dp.message(F.text)
async def handle_chat(message: types.Message):
    await bot.send_chat_action(message.chat.id, "typing")
    response = await ask_ai("Ти корисний асистент.", message.text)
    await message.answer(response)

# --- Запуск ---
async def main():
    init_db()
    
    # Планувальник ( scheduler )
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")
    scheduler.add_job(daily_birthday_check, "cron", hour=9, minute=0)
    scheduler.start()

    # Web server для Render
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🚀 Бот запущений успішно!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
