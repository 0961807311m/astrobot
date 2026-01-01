import sqlite3
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

TOKEN = "8201600405:AAE8upEFnjzz8oBrQJxWYrMyoXyGA7gYGCQ"
MY_ID = 209403052
DB_PATH = "/home/MaxOdn/bot_data.db"

async def check_birthdays():
    today_str = datetime.now().strftime("%d.%m")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%d.%m")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        proxy_session = AiohttpSession(proxy="http://proxy.server:3128")
        bot = Bot(token=TOKEN, session=proxy_session)

        # 1. Перевірка на СЬОГОДНІ
        cursor.execute('SELECT full_name FROM birthdays WHERE birth_date = ?', (today_str,))
        today_res = cursor.fetchall()
        if today_res:
            names = "\n".join([f"• {r[0]}" for r in today_res])
            await bot.send_message(MY_ID, f"🎉 <b>СЬОГОДНІ день народження:</b>\n\n{names}", parse_mode="HTML")

        # 2. Перевірка на ЗАВТРА
        cursor.execute('SELECT full_name FROM birthdays WHERE birth_date = ?', (tomorrow_str,))
        tomorrow_res = cursor.fetchall()
        if tomorrow_res:
            names = "\n".join([f"• {r[0]}" for r in tomorrow_res])
            await bot.send_message(MY_ID, f"⏳ <b>ЗАВТРА день народження:</b>\n\n{names}", parse_mode="HTML")

        conn.close()
        await bot.session.close()

    except Exception as e:
        print(f"Помилка в reminder.py: {e}")

if __name__ == "__main__":
    asyncio.run(check_birthdays())
