import psycopg2
import os

# Отримуємо посилання на базу Neon із налаштувань Render
DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DB_URL, sslmode='require')

def init_db():
    """Створює всі необхідні таблиці в Neon при запуску бота."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Таблиця днів народження
        cur.execute('''CREATE TABLE IF NOT EXISTS birthdays
                       (id SERIAL PRIMARY KEY, user_id BIGINT, full_name TEXT, birth_date TEXT)''')
        
        # 2. Таблиця для ШІ (астро-дані)
        cur.execute('''CREATE TABLE IF NOT EXISTS astro_users
                       (user_id BIGINT PRIMARY KEY, info TEXT)''')
        
        # 3. Таблиця завдань
        cur.execute('''CREATE TABLE IF NOT EXISTS shift_tasks
                       (id SERIAL PRIMARY KEY, user_id BIGINT, task_text TEXT, is_done INTEGER DEFAULT 0)''')
        
        conn.commit()
        print("✅ Всі таблиці в базі даних успішно перевірені/створені")
    except Exception as e:
        print(f"❌ Помилка ініціалізації бази: {e}")
    finally:
        cur.close()
        conn.close()

# --- ФУНКЦІЇ ДЛЯ ДНІВ НАРОДЖЕННЯ ---

def add_birthday(user_id, name, date):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO birthdays (user_id, full_name, birth_date) VALUES (%s, %s, %s)",
            (user_id, name, date)
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_birthdays_by_name(user_id, search_name):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, full_name, birth_date FROM birthdays WHERE user_id = %s AND full_name ILIKE %s",
            (user_id, f"%{search_name}%")
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

# --- ФУНКЦІЇ ДЛЯ ШІ (ASTRO DATA) ---

def save_astro_data(user_id, birth_data):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''INSERT INTO astro_users (user_id, info) VALUES (%s, %s)
                       ON CONFLICT (user_id) DO UPDATE SET info = EXCLUDED.info''', 
                    (user_id, birth_data))
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_astro_data(user_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT info FROM astro_users WHERE user_id = %s", (user_id,))
        res = cur.fetchone()
        return res[0] if res else None
    finally:
        cur.close()
        conn.close()
