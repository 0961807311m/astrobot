import os
import asyncio
import logging
from aiogram import Bot

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")

async def test_auth():
    if not TOKEN:
        logging.error("❌ Змінна BOT_TOKEN порожня!")
        return
    
    bot = Bot(token=TOKEN)
    try:
        me = await bot.get_me()
        logging.info(f"✅ УСПІХ! Бот авторизований: @{me.username}")
    except Exception as e:
        logging.error(f"❌ ПОМИЛКА: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test_auth())
