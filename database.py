import psycopg2
from psycopg2.extras import DictCursor
import os

# Render автоматично підставить це посилання з Environment Variables
DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    """Створює підключення до Neon.tech"""
    return psycopg2.connect(DB_URL, sslmode='require')

def init_db():
    """Ініціалізація таблиць у PostgreSQL (Neon.tech)."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Таблиця для днів народження
    cursor.execute('''CREATE TABLE IF NOT EXISTS birthdays
                      (id SERIAL PRIMARY KEY,
                       user_id BIGINT,
                       full_name TEXT,
                       birth_date TEXT)''')

    # 2. Таблиця для астро-даних ШІ
    cursor.execute('''CREATE TABLE IF NOT EXISTS astro_users
                      (user_id BIGINT PRIMARY KEY,
                       info TEXT)''')

    # 3. Таблиця для завдань на зміну
    cursor.execute('''CREATE TABLE IF NOT EXISTS shift_tasks
                      (id SERIAL PRIMARY KEY,
                       user_id BIGINT,
                       task_text TEXT,
                       is_done INTEGER DEFAULT 0)''')

    conn.commit()
    cursor.close()
    conn.close()

# --- ФУНКЦІЇ ДЛЯ ДНІВ НАРОДЖЕННЯ ---

def add_birthday(user_id, name, date):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO birthdays (user_id, full_name, birth_date) VALUES (%s, %s, %s)',
                   (user_id, name, date))
    conn.commit()
    cursor.close()
    conn.close()

def get_birthdays_by_name(user_id, name):
    conn = get_connection()
    cursor = conn.cursor()
    # ILIKE для пошуку без врахування регістру
    cursor.execute('SELECT id, full_name, birth_date FROM birthdays WHERE user_id = %s AND full_name ILIKE %s',
                   (user_id, f'%{name}%'))
    res = cursor.fetchall()
    cursor.close()
    conn.close()
    return res

def delete_birthday(entry_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM birthdays WHERE id = %s', (entry_id,))
    conn.commit()
    cursor.close()
    conn.close()

# --- ФУНКЦІЇ ДЛЯ ШІ (АСТРОЛОГІЯ) ---

def save_astro_data(user_id, birth_data):
    conn = get_connection()
    cursor = conn.cursor()
    # PostgreSQL використовує ON CONFLICT для аналога REPLACE
    cursor.execute('''INSERT INTO astro_users (user_id, info) VALUES (%s, %s)
                      ON CONFLICT (user_id) DO UPDATE SET info = EXCLUDED.info''',
                   (user_id, birth_data))
    conn.commit()
    cursor.close()
    conn.close()

def get_astro_data(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT info FROM astro_users WHERE user_id = %s', (user_id,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    return res[0] if res else None

# --- ФУНКЦІЇ ДЛЯ ЗАВДАНЬ НА ЗМІНУ ---

def add_task(user_id, task_text):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO shift_tasks (user_id, task_text) VALUES (%s, %s)", (user_id, task_text))
    conn.commit()
    cursor.close()
    conn.close()

def get_tasks(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, task_text, is_done FROM shift_tasks WHERE user_id = %s AND is_done = 0", (user_id,))
    res = cursor.fetchall()
    cursor.close()
    conn.close()
    return res

def complete_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE shift_tasks SET is_done = 1 WHERE id = %s", (task_id,))
    conn.commit()
    cursor.close()
    conn.close()
