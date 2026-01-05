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

# --- Конфігурація ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")
# Використовуємо OpenRouter для стабільного безкоштовного доступу
API_KEY = os.getenv("OPENROUTER_API_KEY") 
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Клієнт для OpenRouter (сумісний з OpenAI)
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY
)

# --- Стани (FSM) ---
class UserProfile(StatesGroup):
    waiting_for_birthday = State()

# --- База даних (з виправленням помилки UndefinedColumn) ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Створення таблиці користувачів
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT);")
        # ПРИМУСОВЕ додавання колонки, якщо її не було
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday DATE;")
        # Таблиця працівників
        cur.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id SERIAL PRIMARY KEY,
                full_name TEXT,
                birth_date DATE
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        logging.info("✅ База даних успішно ініціалізована та оновлена")
    except Exception as e:
        logging.error(f"❌ Помилка БД: {e}")

# --- Меню ---
def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💬 Поговорити")
    builder.button(text="✨ Порада дня")
    builder.button(text="🎂 Дні народження")
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

# --- Логіка ШІ ---
async def ask_ai(system_prompt, user_prompt):
    try:
        response = client.chat.completions.create(
            # Безкоштовна актуальна модель Llama 3.1 від OpenRouter
            model="meta-llama/llama-3.1-8b-instruct:free",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            extra_headers={
                "HTTP-Referer": "https://render.com", # Обов'язково для OpenRouter
                "X-Title": "My Astro Bot"
            }
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"AI Error: {e}")
        return "⚠️ ШІ зараз розмірковує надто довго. Спробуйте за хвилину!"

# --- Обробники повідомлень ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    init_db()
    await message.answer(
        f"Привіт, {message.from_user.first_name}! 🚀\nЯ твій персональний асистент. Оберіть дію:",
        reply_markup=main_menu_kb()
    )

@dp.message(F.text == "💬 Поговорити")
async def talk_mode(message: types.Message):
    await message.answer("Я весь в увазі! Про що хочеш поспілкуватися?")

@dp.message(F.text == "✨ Порада дня")
async def astro_advice(message: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT birthday FROM users WHERE user_id = %s", (message.from_user.id,))
    res = cur.fetchone()
    cur.close()
    conn.close()

    if not res or not res[0]:
        await message.answer("Для точного розрахунку введіть дату народження у форматі: **ДД.ММ.РРРР**\n(Наприклад: 12.04.1992)")
        await state.set_state(UserProfile.waiting_for_birthday)
    else:
        await bot.send_chat_action(message.chat.id, "typing")
        bday = res[0].strftime("%d.%m.%Y")
        
        system_prompt = "Ти професійний коуч та експерт з саморозвитку. Надаєш поради на основі Матриці Долі (астрологія та нумерологія), але без магічного жаргону. Твій стиль: аналітичний, надихаючий."
        user_prompt = (
            f"Дата народження користувача: {bday}. Сьогоднішня дата: {datetime.now().strftime('%d.%m.%Y')}. "
            "Напиши коротку пораду дня. Обов'язково виділи пункти: "
            "1. Чого очікувати. 2. Чого уникати. 3. Енергія дня у балах (від 0 до 100). Відповідай українською."
        )
        
        advice = await ask_ai(system_prompt, user_prompt)
        await message.answer(f"🔮 **Твій прогноз за Матрицею Долі:**\n\n{advice}")

@dp.message(UserProfile.waiting_for_birthday)
async def process_bday(message: types.Message, state: FSMContext):
    try:
        bday = datetime.strptime(message.text, "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, birthday) 
            VALUES (%s, %s, %s) 
            ON CONFLICT (user_id) DO UPDATE SET birthday = EXCLUDED.birthday
        """, (message.from_user.id, message.from_user.username, bday))
        conn.commit()
        cur.close()
        conn.close()
        
        await message.answer("✅ Дату збережено! Тепер тисни '✨ Порада дня' знову.", reply_markup=main_menu_kb())
        await state.clear()
    except ValueError:
        await message.answer("❌ Невірний формат. Будь ласка, напиши дату як ДД.ММ.РРРР (наприклад: 01.01.2000)")

@dp.message(F.text == "🎂 Дні народження")
async def check_birthdays(message: types.Message):
    today = datetime.now().strftime("%m-%d")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT full_name FROM employees WHERE to_char(birth_date, 'MM-DD') = %s", (today,))
    workers = cur.fetchall()
    cur.close()
    conn.close()

    if workers:
        text = "🎉 **Сьогодні іменинники серед колег:**\n\n" + "\n".join([f"🎂 {w[0]}" for w in workers])
        await message.answer(text)
    else:
        await message.answer("Сьогодні іменинників серед працівників немає. ✨")

# --- Веб-сервер для Render ---
async def handle_ping(request): return web.Response(text="OK")

async def main():
    init_db()
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 10000).start()
    
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🚀 Бот запущений!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
