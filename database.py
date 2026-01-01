import psycopg2
import os

DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DB_URL, sslmode='require')

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS birthdays
                   (id SERIAL PRIMARY KEY, user_id BIGINT, full_name TEXT, birth_date TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS astro_users
                   (user_id BIGINT PRIMARY KEY, info TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS shift_tasks
                   (id SERIAL PRIMARY KEY, user_id BIGINT, task_text TEXT, is_done INTEGER DEFAULT 0)''')
    conn.commit()
    cur.close()
    conn.close()

def add_birthday(user_id, name, date):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO birthdays (user_id, full_name, birth_date) VALUES (%s, %s, %s)", (user_id, name, date))
    conn.commit()
    cur.close()
    conn.close()

def get_birthdays_by_name(user_id, search_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, full_name, birth_date FROM birthdays WHERE user_id = %s AND full_name ILIKE %s", (user_id, f"%{search_name}%"))
    res = cur.fetchall()
    cur.close()
    conn.close()
    return res

def delete_birthday(entry_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM birthdays WHERE id = %s", (entry_id,))
    conn.commit()
    cur.close()
    conn.close()
