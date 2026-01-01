import psycopg2
import os

# Render автоматично підтягне це з налаштувань Environment
DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DB_URL, sslmode='require')

def init_db():
    """Створює таблиці в Neon, якщо їх ще немає."""
    conn = get_connection()
    cur = conn.cursor()
    # Таблиця днів народження
    cur.execute('''CREATE TABLE IF NOT EXISTS birthdays
                   (id SERIAL PRIMARY KEY, user_id BIGINT, full_name TEXT, birth_date TEXT)''')
    # Таблиця для ШІ
    cur.execute('''CREATE TABLE IF NOT EXISTS astro_users
                   (user_id BIGINT PRIMARY KEY, info TEXT)''')
    # Таблиця завдань
    cur.execute('''CREATE TABLE IF NOT EXISTS shift_tasks
                   (id SERIAL PRIMARY KEY, user_id BIGINT, task_text TEXT, is_done INTEGER DEFAULT 0)''')
    conn.commit()
    cur.close()
    conn.close()

def save_astro_data(user_id, birth_data):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''INSERT INTO astro_users (user_id, info) VALUES (%s, %s)
                   ON CONFLICT (user_id) DO UPDATE SET info = EXCLUDED.info''', (user_id, birth_data))
    conn.commit()
    cur.close()
    conn.close()

def get_astro_data(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT info FROM astro_users WHERE user_id = %s", (user_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res[0] if res else None

# Додайте сюди інші функції (add_birthday, add_task тощо), замінивши ? на %s
