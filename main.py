import os
import asyncio
import logging
import psycopg2
import pytz
import json
import base64
import aiohttp
import re
import signal
import sys
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from PIL import Image, ImageEnhance
from io import BytesIO

# --- НАЛАШТУВАННЯ ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
KYIV_TZ = pytz.timezone("Europe/Kyiv")

# API ключі
GEMINI_API_KEY = "AIzaSyDF02DF1mWlzY9LbykDp5SL9fsJhNd9Hxo"
SMS_FLY_API_KEY = os.getenv("SMS_FLY_API_KEY", "t1G7njJlTFjmCJRs7HV96ZLG2gmND9O5")
SMS_FLY_SENDER = os.getenv("SMS_FLY_SENDER", "YourBot")

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=KYIV_TZ)

# Глобальні змінні для graceful shutdown
shutdown_event = asyncio.Event()
web_runner = None

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
    waiting_for_medical_photo = State()
    waiting_for_sunday_photo = State()

# --- SMS FLY КЛІЄНТ ---
class SMSFlyClient:
    def __init__(self, api_key: str, sender: str = "YourBot"):
        self.api_key = api_key
        self.sender = sender
        self.base_url = "https://sms-fly.ua/api/v2/api.php"

    async def send_sms(self, phone: str, message: str, ttl: int = 60, flash: int = 0):
        phone = ''.join(filter(str.isdigit, phone))
        if phone.startswith('0'):
            phone = '380' + phone[1:]
        elif phone.startswith('8'):
            phone = '380' + phone[1:]
        elif not phone.startswith('380'):
            phone = '380' + phone
            
        payload = {
            "auth": {"key": self.api_key},
            "action": "SENDMESSAGE",
            "data": {
                "recipient": phone,
                "channels": ["sms"],
                "sms": {
                    "source": self.sender,
                    "ttl": ttl,
                    "flash": flash,
                    "text": message
                }
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') == 1:
                            return {"success": True, "message_id": data.get('data', {}).get('messageID')}
                        else:
                            error = data.get('error', {})
                            return {"success": False, "error": error.get('description')}
                    return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def get_extended_balance(self):
        payload = {
            "auth": {"key": self.api_key},
            "action": "GETBALANCEEXT",
            "data": {}
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') == 1:
                            balance_data = data.get('data', {}).get('balance', {})
                            return {"success": True, "sms_balance": balance_data.get('sms', '0'), "viber_balance": balance_data.get('viber', '0')}
                        return {"success": False, "error": "API error"}
                    return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

sms_client = SMSFlyClient(SMS_FLY_API_KEY, SMS_FLY_SENDER)

# --- БАЗА ДАНИХ ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, shift_type TEXT DEFAULT 'day');")
        cur.execute("CREATE TABLE IF NOT EXISTS employees (id SERIAL PRIMARY KEY, full_name TEXT, birth_date DATE);")
        cur.execute("CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT, is_done BOOLEAN DEFAULT FALSE);")
        cur.execute("CREATE TABLE IF NOT EXISTS routes (id SERIAL PRIMARY KEY, info TEXT);")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS employee_phones (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_employee_phones_name ON employee_phones(full_name);")
        try:
            cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS remind_at TIMESTAMP;")
        except:
            conn.rollback()
        conn.commit()
        cur.close()
        conn.close()
        logger.info("✅ База даних ініціалізована")
    except Exception as e:
        logger.error(f"❌ Помилка ініціалізації БД: {e}")

def get_employee_phone(full_name):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        short_name = full_name.split()[0] if ' ' in full_name else full_name
        cur.execute("SELECT phone FROM employee_phones WHERE full_name ILIKE %s LIMIT 1", (f"%{short_name}%",))
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Помилка отримання телефону: {e}")
        return None

# --- ФУНКЦІЯ СТИСНЕННЯ ЗОБРАЖЕННЯ ---
async def compress_image(image_bytes, max_size=800, quality=60):
    try:
        img = Image.open(BytesIO(image_bytes))
        
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        ratio = max_size / max(img.width, img.height)
        if ratio < 1:
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.3)
        
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        
        compressed = buffer.getvalue()
        original_size = len(image_bytes) / 1024
        compressed_size = len(compressed) / 1024
        
        logger.info(f"Стиснення: {original_size:.1f}KB -> {compressed_size:.1f}KB (економія {original_size - compressed_size:.1f}KB)")
        
        return compressed
    except Exception as e:
        logger.error(f"Помилка стиснення: {e}")
        return image_bytes

# --- ФУНКЦІЯ АНАЛІЗУ ТАБЛИЦЬ ЧЕРЕЗ GEMINI 2.5 FLASH ---
async def analyze_table_with_gemini(image_bytes, table_type="medical"):
    compressed_image = await compress_image(image_bytes, max_size=800, quality=60)
    image_base64 = base64.b64encode(compressed_image).decode('utf-8')
    
    if table_type == "medical":
        prompt = """Ти експерт з розпізнавання таблиць. На фото таблиця медоглядів.
Колонки: Прізвище, Медогляд, Флюорографія, Гінеколог, Вакцинація.
Позначки "потрібно" = "так", "ні" = "ні".
Відповідай ТІЛЬКИ JSON без пояснень. Ось приклад правильної відповіді:
[{"name": "Акенттій", "medical": "ні", "fluorography": "так", "gynecology": "ні", "vaccination": "ні"}]
"""
    else:
        prompt = """Ти експерт з розпізнавання таблиць. На фото таблиця роботи в неділю.
Відповідай ТІЛЬКИ JSON: [{"name": "Прізвище", "need_to_work": "так/ні"}]
Приклад: [{"name": "Костюк", "need_to_work": "так"}]"""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}}
            ]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096  # ЗБІЛЬШЕНО для повної відповіді
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=120) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'candidates' in data and len(data['candidates']) > 0:
                        result_text = data['candidates'][0]['content']['parts'][0]['text']
                        logger.info(f"Gemini відповів: {result_text[:500]}")
                        
                        # Очищаємо відповідь від маркерів
                        result_text = result_text.strip()
                        if result_text.startswith('```json'):
                            result_text = result_text[7:]
                        if result_text.startswith('```'):
                            result_text = result_text[3:]
                        if result_text.endswith('```'):
                            result_text = result_text[:-3]
                        
                        # Шукаємо JSON масив
                        json_match = re.search(r'\[\s*\{.*\}\s*\]', result_text, re.DOTALL)
                        if json_match:
                            result_text = json_match.group()
                        
                        # Додаткова перевірка на неповний JSON
                        try:
                            result = json.loads(result_text)
                            logger.info(f"Розпізнано {len(result)} працівників")
                            return result
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON помилка: {e}")
                            # Спроба виправити неповний JSON
                            if result_text.endswith(','):
                                result_text = result_text[:-1] + "}]"
                            elif not result_text.endswith(']'):
                                result_text = result_text + "}]"
                            try:
                                result = json.loads(result_text)
                                return result
                            except:
                                return None
                    else:
                        logger.error(f"No candidates in response: {data}")
                        return None
                elif resp.status == 403:
                    logger.error("API ключ заблоковано! Отримайте новий ключ")
                    return None
                else:
                    error_text = await resp.text()
                    logger.error(f"Gemini API error {resp.status}: {error_text}")
                    return None
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return None

# --- ГОЛОВНЕ МЕНЮ ---
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📋 Завдання на зміну")
    builder.button(text="🚍 Маршрути")
    builder.button(text="⚙️ Зміна")
    builder.button(text="🎂 Дні народження")
    builder.button(text="🏥 Медпункт")
    builder.button(text="📅 Робота в неділю")
    builder.button(text="💰 Баланс SMS")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)

# --- 1. START ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    init_db()
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING", 
                (m.from_user.id, m.from_user.username))
    conn.commit()
    cur.close()
    conn.close()
    await m.answer("👋 Вітаю! Я оновився і готовий до роботи.", reply_markup=main_menu())

# --- 2. ЗАВДАННЯ ---
async def get_tasks_kb():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, title, is_done, remind_at FROM tasks ORDER BY id ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    kb = InlineKeyboardBuilder()
    for tid, title, done, remind_at in rows:
        icon = "✅" if done else "⬜"
        clock = "⏰" if (remind_at and not done) else ""
        kb.button(text=f"{icon} {title} {clock}", callback_data=f"tgl_{tid}")
    kb.adjust(1)
    kb.row(types.InlineKeyboardButton(text="➕ Додати", callback_data="t_add"),
           types.InlineKeyboardButton(text="🗑 Видалити", callback_data="t_del_menu"))
    return kb.as_markup()

@dp.message(F.text == "📋 Завдання на зміну")
async def show_tasks(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("📝 Список завдань:", reply_markup=await get_tasks_kb())

@dp.callback_query(F.data.startswith("tgl_"))
async def toggle_task(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET is_done = NOT is_done, remind_at = NULL WHERE id = %s", (tid,))
    conn.commit()
    cur.execute("SELECT count(*) FROM tasks WHERE is_done = FALSE")
    remaining = cur.fetchone()[0]
    cur.close()
    conn.close()
    await c.message.edit_reply_markup(reply_markup=await get_tasks_kb())
    if remaining == 0:
        await c.message.answer("🎉 Усі завдання виконано!")
    await c.answer()

@dp.callback_query(F.data == "t_add")
async def t_add_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("✍️ Напишіть назву завдання:")
    await state.set_state(BotStates.waiting_for_task_name)

@dp.message(BotStates.waiting_for_task_name)
async def t_add_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO tasks (title) VALUES (%s) RETURNING id", (m.text,))
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    kb = InlineKeyboardBuilder()
    kb.button(text="⏰ Через 1 год", callback_data=f"rem_{new_id}_60")
    kb.button(text="⏰ Через 2 год", callback_data=f"rem_{new_id}_120")
    kb.button(text="❌ Без нагадування", callback_data="rem_skip")
    kb.adjust(2, 1)
    await m.answer(f"✅ Завдання '{m.text}' створено! Нагадати про нього?", reply_markup=kb.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("rem_"))
async def set_reminder(c: types.CallbackQuery):
    if c.data == "rem_skip":
        await c.message.edit_text("✅ Завдання додано без нагадування.", reply_markup=await get_tasks_kb())
        return
    parts = c.data.split("_")
    tid = int(parts[1])
    minutes = int(parts[2])
    remind_time = datetime.now(KYIV_TZ) + timedelta(minutes=minutes)
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET remind_at = %s WHERE id = %s", (remind_time, tid))
    conn.commit()
    cur.close()
    conn.close()
    await c.message.edit_text(f"✅ Нагадування встановлено на {remind_time.strftime('%H:%M')}!", reply_markup=await get_tasks_kb())

@dp.callback_query(F.data == "t_del_menu")
async def t_del_menu(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM tasks")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    kb = InlineKeyboardBuilder()
    for tid, title in rows:
        kb.button(text=f"❌ {title}", callback_data=f"tdel_{tid}")
    kb.adjust(1)
    kb.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="t_back"))
    await c.message.edit_text("🗑 Видалення завдань:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("tdel_"))
async def t_del_exec(c: types.CallbackQuery):
    tid = int(c.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id = %s", (tid,))
    conn.commit()
    cur.close()
    conn.close()
    await c.answer("Видалено")
    await c.message.edit_text("📝 Список завдань:", reply_markup=await get_tasks_kb())

@dp.callback_query(F.data == "t_back")
async def t_back(c: types.CallbackQuery):
    await c.message.edit_text("📝 Список завдань:", reply_markup=await get_tasks_kb())

# --- 3. МАРШРУТИ ---
@dp.message(F.text == "🚍 Маршрути")
async def show_routes(m: types.Message, state: FSMContext):
    await state.clear()
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, info FROM routes ORDER BY id ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    txt = "🚍 **Маршрути розвозки:**\n\n" + ("-" if not rows else "\n".join([f"📍 {r[1]}" for r in rows]))
    kb = InlineKeyboardBuilder().button(text="➕ Додати", callback_data="r_add").button(text="🗑 Видалити", callback_data="r_del_list").adjust(2)
    await m.answer(txt, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "r_add")
async def r_add_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Введіть дані (Прізвище - Зупинка):")
    await state.set_state(BotStates.waiting_for_route_data)

@dp.message(BotStates.waiting_for_route_data)
async def r_add_save(m: types.Message, state: FSMContext):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("INSERT INTO routes (info) VALUES (%s)", (m.text,))
    conn.commit()
    cur.close()
    conn.close()
    await m.answer("✅ Зупинку додано!")
    await state.clear()

@dp.callback_query(F.data == "r_del_list")
async def r_del_list(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, info FROM routes")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    kb = InlineKeyboardBuilder()
    for rid, info in rows:
        kb.button(text=f"❌ {info[:20]}", callback_data=f"rdel_{rid}")
    kb.adjust(1).row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="r_back_main"))
    await c.message.edit_text("🗑 Оберіть зупинку для видалення:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("rdel_"))
async def r_del_exec(c: types.CallbackQuery):
    rid = int(c.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM routes WHERE id = %s", (rid,))
    conn.commit()
    cur.close()
    conn.close()
    await c.answer("Видалено")
    await r_del_list(c)

@dp.callback_query(F.data == "r_back_main")
async def r_back(c: types.CallbackQuery, state: FSMContext):
    await show_routes(c.message, state)
    await c.answer()

# --- 4. ДНІ НАРОДЖЕННЯ ---
@dp.message(F.text == "🎂 Дні народження")
async def bday_menu(m: types.Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder().button(text="➕ Додати", callback_data="e_add").button(text="📜 Список", callback_data="e_list").button(text="🗑 Видалити", callback_data="e_del_l").adjust(2, 1)
    await m.answer("🎂 Керування іменинниками:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "e_list")
async def e_list(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT full_name, birth_date FROM employees ORDER BY EXTRACT(MONTH FROM birth_date), EXTRACT(DAY FROM birth_date)")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    res = {"Керівники": [], "Працівники": []}
    for name, date in rows:
        line = f"{date.strftime('%d.%m')} — {name}"
        if any(m_name in name for m_name in MANAGERS_NAMES):
            res["Керівники"].append(line)
        else:
            res["Працівники"].append(line)
    txt = "📜 **СПИСОК:**\n\n⭐ **КЕРІВНИКИ:**\n" + ("-" if not res["Керівники"] else "\n".join(res["Керівники"]))
    txt += "\n\n👥 **ПРАЦІВНИКИ:**\n" + ("-" if not res["Працівники"] else "\n".join(res["Працівники"]))
    await c.message.answer(txt, parse_mode="Markdown")
    await c.answer()

@dp.callback_query(F.data == "e_add")
async def e_add_start(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("Пришліть: Прізвище Ім'я - ДД.ММ.РРРР")
    await state.set_state(BotStates.waiting_for_employee_data)

@dp.message(BotStates.waiting_for_employee_data)
async def e_add_save(m: types.Message, state: FSMContext):
    try:
        p = m.text.split(" - ")
        d = datetime.strptime(p[1].strip(), "%d.%m.%Y").date()
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("INSERT INTO employees (full_name, birth_date) VALUES (%s, %s)", (p[0].strip(), d))
        conn.commit()
        cur.close()
        conn.close()
        await m.answer("✅ Успішно додано!")
        await state.clear()
    except:
        await m.answer("❌ Помилка. Формат: Шевченко Тарас - 09.03.1814")

@dp.callback_query(F.data == "e_del_l")
async def e_del_l(c: types.CallbackQuery):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, full_name FROM employees ORDER BY full_name")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    kb = InlineKeyboardBuilder()
    for eid, name in rows:
        kb.button(text=f"🗑 {name[:25]}", callback_data=f"ed_{eid}")
    kb.adjust(1)
    await c.message.edit_text("🗑 Кого видалити?", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("ed_"))
async def e_del_do(c: types.CallbackQuery):
    eid = int(c.data.split("_")[1])
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM employees WHERE id = %s", (eid,))
    conn.commit()
    cur.close()
    conn.close()
    await c.answer("Видалено!")
    await e_list(c)

# --- 5. ЗМІНА ---
@dp.message(F.text == "⚙️ Зміна")
async def change_shift(m: types.Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder().button(text="☀️ День", callback_data="s_day").button(text="🌙 Ніч", callback_data="s_night").adjust(1)
    await m.answer("Оберіть Вашу зміну:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("s_"))
async def set_shift(c: types.CallbackQuery):
    s = "day" if "day" in c.data else "night"
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE users SET shift_type = %s WHERE user_id = %s", (s, c.from_user.id))
    conn.commit()
    cur.close()
    conn.close()
    await c.message.answer(f"✅ Встановлено графік: {s.upper()}")
    await c.answer()

# --- 6. БАЛАНС SMS ---
@dp.message(F.text == "💰 Баланс SMS")
async def check_sms_balance(message: types.Message):
    wait_msg = await message.answer("🔄 Перевіряю баланс...")
    balance = await sms_client.get_extended_balance()
    if balance.get('success'):
        await wait_msg.edit_text(f"💰 **Баланс SMS Fly:**\n\n📱 SMS: {balance.get('sms_balance', '0')} грн\n💬 Viber: {balance.get('viber_balance', '0')} грн", parse_mode="Markdown")
    else:
        await wait_msg.edit_text(f"❌ **Помилка:** {balance.get('error', 'Невідома помилка')}", parse_mode="Markdown")

# --- 7. МЕДПУНКТ ---
@dp.message(F.text == "🏥 Медпункт")
async def medical_start(message: types.Message, state: FSMContext):
    await message.answer(
        "🏥 **Медичний огляд працівників**\n\n"
        "📸 **Сфотографуйте таблицю** з графіком медоглядів.\n\n"
        "⚡ *Використовується Gemini 2.5 Flash*\n"
        "💡 *Фотографуйте чітко, при хорошому освітленні*",
        parse_mode="Markdown"
    )
    await state.set_state(BotStates.waiting_for_medical_photo)

@dp.message(BotStates.waiting_for_medical_photo, F.photo)
async def process_medical_photo(message: types.Message, state: FSMContext, bot: Bot):
    wait_msg = await message.answer("🔍 **Аналізую таблицю...**\n(це займе 5-10 секунд)", parse_mode="Markdown")
    
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        
        employees = await analyze_table_with_gemini(file_bytes.read(), "medical")
        
        if not employees:
            await wait_msg.edit_text(
                "❌ **Не вдалося розпізнати таблицю.**\n\n"
                "💡 Спробуйте сфотографувати ще раз.",
                parse_mode="Markdown"
            )
            await state.clear()
            return
        
        result = "📋 **Результат аналізу:**\n\n"
        employees_with_needs = []
        
        for emp in employees:
            needs = []
            if emp.get('medical') == 'так':
                needs.append("М")
            if emp.get('fluorography') == 'так':
                needs.append("Ф")
            if emp.get('gynecology') == 'так':
                needs.append("Г")
            if emp.get('vaccination') == 'так':
                needs.append("В")
            
            if needs:
                result += f"• **{emp['name']}**: {', '.join(needs)}\n"
                employees_with_needs.append(emp)
            else:
                result += f"• **{emp['name']}**: ✅ всі огляди пройдено\n"
        
        if not employees_with_needs:
            await wait_msg.edit_text(result + "\n\n✅ **Всі працівники пройшли огляди!**", parse_mode="Markdown")
            await state.clear()
            return
        
        await state.update_data(medical_employees=employees_with_needs)
        
        kb = InlineKeyboardBuilder()
        kb.button(text="✉️ Відправити SMS", callback_data="send_medical_sms")
        kb.button(text="❌ Скасувати", callback_data="cancel_medical")
        kb.adjust(1)
        
        await wait_msg.edit_text(
            result + "\n\n⚠️ **Відправити SMS нагадування?**",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Medical error: {e}")
        await wait_msg.edit_text(f"❌ **Помилка обробки фото:** {str(e)[:100]}", parse_mode="Markdown")
        await state.clear()

@dp.callback_query(F.data == "send_medical_sms")
async def send_medical_sms(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    employees = data.get('medical_employees', [])
    
    if not employees:
        await callback.answer("Немає даних для відправки")
        await state.clear()
        return
    
    await callback.message.edit_text(f"📤 **Відправляю SMS {len(employees)} працівникам...**\nБудь ласка, зачекайте.", parse_mode="Markdown")
    
    results = []
    for emp in employees:
        phone = get_employee_phone(emp['name'])
        
        if phone:
            needs_short = []
            if emp.get('medical') == 'так':
                needs_short.append("М")
            if emp.get('fluorography') == 'так':
                needs_short.append("Ф")
            if emp.get('gynecology') == 'так':
                needs_short.append("Г")
            if emp.get('vaccination') == 'так':
                needs_short.append("Щ")
            
            if needs_short:
                msg = f"Потрібне медобстеження: {', '.join(needs_short)}"
                result = await sms_client.send_sms(phone, msg)
                results.append({"name": emp['name'], "success": result['success'], "phone": phone, "needs": needs_short})
            else:
                results.append({"name": emp['name'], "success": None, "phone": None})
        else:
            results.append({"name": emp['name'], "success": False, "error": "немає телефону"})
    
    success_count = sum(1 for r in results if r.get('success') is True)
    no_phone_count = sum(1 for r in results if r.get('error') == "немає телефону")
    
    report = f"📊 **Звіт про відправку SMS:**\n\n"
    report += f"✅ Успішно: {success_count}\n"
    report += f"📭 Немає телефону: {no_phone_count}\n"
    report += f"❌ Помилок: {len(employees) - success_count - no_phone_count}\n\n"
    
    if results:
        report += "**Деталі:**\n"
        for r in results:
            if r.get('success') is True:
                report += f"✅ {r['name']}: {', '.join(r.get('needs', []))}\n"
            elif r.get('error') == "немає телефону":
                report += f"📭 {r['name']} - немає номера\n"
            else:
                report += f"❌ {r['name']} - помилка\n"
    
    await callback.message.edit_text(report, parse_mode="Markdown")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "cancel_medical")
async def cancel_medical(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ Операцію скасовано. SMS не відправлено.")
    await state.clear()
    await callback.answer()

# --- 8. РОБОТА В НЕДІЛЮ ---
@dp.message(F.text == "📅 Робота в неділю")
async def sunday_start(message: types.Message, state: FSMContext):
    await message.answer(
        "📅 **Графік роботи в неділю**\n\n"
        "📸 **Сфотографуйте таблицю** з графіком роботи.\n\n"
        "⚡ *Використовується Gemini 2.5 Flash*\n"
        "💡 *Фотографуйте чітко, при хорошому освітленні*",
        parse_mode="Markdown"
    )
    await state.set_state(BotStates.waiting_for_sunday_photo)

@dp.message(BotStates.waiting_for_sunday_photo, F.photo)
async def process_sunday_photo(message: types.Message, state: FSMContext, bot: Bot):
    wait_msg = await message.answer("🔍 **Аналізую таблицю...**\n(це займе 5-10 секунд)", parse_mode="Markdown")
    
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        
        employees = await analyze_table_with_gemini(file_bytes.read(), "sunday")
        
        if not employees:
            await wait_msg.edit_text(
                "❌ **Не вдалося розпізнати таблицю.**\n\n"
                "💡 Спробуйте сфотографувати ще раз.",
                parse_mode="Markdown"
            )
            await state.clear()
            return
        
        workers = [emp for emp in employees if emp.get('need_to_work') == 'так']
        
        if not workers:
            await wait_msg.edit_text("📭 **За графіком ніхто не працює в неділю.**", parse_mode="Markdown")
            await state.clear()
            return
        
        result = "📋 **Працівники, які працюють в неділю:**\n\n"
        for w in workers:
            result += f"• **{w['name']}**\n"
        
        await state.update_data(sunday_workers=workers)
        
        kb = InlineKeyboardBuilder()
        kb.button(text="✉️ Відправити SMS", callback_data="send_sunday_sms")
        kb.button(text="❌ Скасувати", callback_data="cancel_sunday")
        kb.adjust(1)
        
        await wait_msg.edit_text(
            result + "\n\n⚠️ **Відправити SMS нагадування?**",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Sunday error: {e}")
        await wait_msg.edit_text(f"❌ **Помилка обробки фото:** {str(e)[:100]}", parse_mode="Markdown")
        await state.clear()

@dp.callback_query(F.data == "send_sunday_sms")
async def send_sunday_sms(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    workers = data.get('sunday_workers', [])
    
    if not workers:
        await callback.answer("Немає даних для відправки")
        await state.clear()
        return
    
    await callback.message.edit_text(f"📤 **Відправляю SMS {len(workers)} працівникам...**\nБудь ласка, зачекайте.", parse_mode="Markdown")
    
    results = []
    for worker in workers:
        phone = get_employee_phone(worker['name'])
        
        if phone:
            msg = f"Вітаю! В неділю очікуємо на зміні."
            result = await sms_client.send_sms(phone, msg)
            results.append({"name": worker['name'], "success": result['success'], "phone": phone})
        else:
            results.append({"name": worker['name'], "success": False, "error": "немає телефону"})
    
    success_count = sum(1 for r in results if r.get('success') is True)
    no_phone_count = sum(1 for r in results if r.get('error') == "немає телефону")
    
    report = f"📊 **Звіт про відправку SMS:**\n\n"
    report += f"✅ Успішно: {success_count}\n"
    report += f"📭 Немає телефону: {no_phone_count}\n"
    report += f"❌ Помилок: {len(workers) - success_count - no_phone_count}\n\n"
    
    if results:
        report += "**Деталі:**\n"
        for r in results:
            if r.get('success') is True:
                report += f"✅ {r['name']}\n"
            elif r.get('error') == "немає телефону":
                report += f"📭 {r['name']} - немає номера\n"
            else:
                report += f"❌ {r['name']} - помилка\n"
    
    await callback.message.edit_text(report, parse_mode="Markdown")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "cancel_sunday")
async def cancel_sunday(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ Операцію скасовано. SMS не відправлено.")
    await state.clear()
    await callback.answer()

# --- 9. НАГАДУВАННЯ ---
async def global_check():
    try:
        now = datetime.now(KYIV_TZ)
        t = now.strftime("%H:%M")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT user_id, shift_type FROM users")
        users = cur.fetchall()
        
        if t == "09:00":
            cur.execute("SELECT full_name FROM employees WHERE EXTRACT(MONTH FROM birth_date) = %s AND EXTRACT(DAY FROM birth_date) = %s", (now.month, now.day))
            bdays = cur.fetchall()
            if bdays:
                names = "\n".join([f"🎉 {b[0]}" for b in bdays])
                msg = f"🎂 **Сьогодні святкують:**\n\n{names}\n\nНе забудьте привітати!"
                for uid, _ in users:
                    try: await bot.send_message(uid, msg, parse_mode="Markdown")
                    except: pass
        
        for uid, s in users:
            msg = None
            if s == 'night' and t == "02:45":
                msg = "⚡ **Нагадування:** Зафіксувати лічильники!"
            elif s == 'day' and t == "16:40":
                msg = "⚡ **Нагадування:** Зафіксувати лічильники!"
            if now.weekday() <= 4:
                if s == 'day' and t == "07:43":
                    msg = "🔔 **Нагадування:** Подайте кількість персоналу!"
                elif s == 'night' and t == "16:43":
                    msg = "🔔 **Нагадування:** Подайте кількість персоналу!"
            if msg:
                try: await bot.send_message(uid, msg, parse_mode="Markdown")
                except: pass
        
        cur.execute("SELECT id, title FROM tasks WHERE is_done = FALSE AND remind_at IS NOT NULL AND remind_at <= %s", (now,))
        due_tasks = cur.fetchall()
        for tid, title in due_tasks:
            for uid, _ in users:
                try:
                    kb = InlineKeyboardBuilder()
                    kb.button(text="✅ Виконано", callback_data=f"tgl_{tid}")
                    await bot.send_message(uid, f"⏰ **НАГАДУВАННЯ:**\n{title}", reply_markup=kb.as_markup(), parse_mode="Markdown")
                except: pass
            next_remind = now + timedelta(hours=1)
            cur.execute("UPDATE tasks SET remind_at = %s WHERE id = %s", (next_remind, tid))
            conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Global check error: {e}")

# --- 10. ЗАГАЛЬНИЙ ОБРОБНИК ---
@dp.message()
async def any_msg(m: types.Message):
    await m.answer("Будь ласка, використовуйте меню 👇", reply_markup=main_menu())

# --- GRACEFUL SHUTDOWN ---
async def shutdown():
    logger.info("Отримано сигнал завершення...")
    shutdown_event.set()
    scheduler.shutdown(wait=False)
    if web_runner:
        await web_runner.cleanup()
    await bot.session.close()
    logger.info("Бот зупинено")
    sys.exit(0)

def signal_handler():
    asyncio.create_task(shutdown())

# --- ЗАПУСК ---
async def main():
    global web_runner
    
    init_db()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda s, f: asyncio.create_task(shutdown()))
    
    # ВАЖЛИВО: Зупиняємо webhook перед запуском polling
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.sleep(2)
    
    scheduler.add_job(global_check, "interval", minutes=1)
    scheduler.start()
    
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    web_runner = web.AppRunner(app)
    await web_runner.setup()
    site = web.TCPSite(web_runner, '0.0.0.0', 10000)
    await site.start()
    
    logger.info("🚀 Бот успішно запущено з Gemini 2.5 Flash!")
    
    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("Polling cancelled")
    finally:
        await shutdown()

if __name__ == "__main__":
    asyncio.run(main())
