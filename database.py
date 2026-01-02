# --- ФУНКЦІЇ ДЛЯ АСТРО-ДАНИХ (ШІ) ---

def save_astro_data(user_id, birth_data):
    """Зберігає або оновлює дані користувача для ШІ."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''INSERT INTO astro_users (user_id, info) VALUES (%s, %s)
                       ON CONFLICT (user_id) DO UPDATE SET info = EXCLUDED.info''', 
                    (user_id, birth_data))
        conn.commit()
    except Exception as e:
        print(f"Помилка save_astro_data: {e}")
    finally:
        cur.close()
        conn.close()

def get_astro_data(user_id):
    """Отримує збережені дані користувача для формування запиту до ШІ."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT info FROM astro_users WHERE user_id = %s", (user_id,))
        res = cur.fetchone()
        return res[0] if res else None
    except Exception as e:
        print(f"Помилка get_astro_data: {e}")
        return None
    finally:
        cur.close()
        conn.close()
