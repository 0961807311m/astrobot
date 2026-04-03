import os
from dotenv import load_dotenv

load_dotenv()

# Основні налаштування
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 10000))

# API ключі
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash"  # Можна змінити на gemini-2.5-flash коли вийде

# SMS Fly налаштування
SMS_FLY_API_KEY = os.getenv("SMS_FLY_API_KEY")
SMS_FLY_SENDER = os.getenv("SMS_FLY_SENDER", "YourBot")  # Ім'я відправника

# Проксі (якщо потрібно)
PROXY_URL = os.getenv("PROXY_URL")

# Список керівників
MANAGERS_NAMES = [
    "Костюк Леся", "Склярук Анатолій", "Квартюк Іван", 
    "Коваль Мирослава", "Селіверстов Олег", "Хоха", 
    "Полігас Андрій", "Козак Олег", "Лиховид Сергій Миколайович",
    "Маснюк Олександр", "Москаленко Вова", "Людяний Олександр",
    "Лиховид Юра", "Кравець Михайло", "Влага Анатолій",
    "Рутковська Діана", "Манченко Сергій", "Кушнір Андрій",
    "Склярук Тетяна", "Островий Сергій", "Семеніхін Олексій",
    "Кравченко Ігор", "Бойко Тетяна", "Влага Ганна"
]

# Часи нагадувань
REMINDER_TIMES = {
    "night_counters": "02:45",
    "day_counters": "16:40",
    "day_staff": "07:43",
    "night_staff": "16:43"
}

# Чек-лист початку зміни
SHIFT_CHECKLIST = [
    "Подати персонал до 16:50",
    "Склад ТМЦ",
    "Перевірити кількість тари та утіля",
    "Переглянути план 1.26 тари",
    "Черга авто логістика",
    "Заповнити журнали"
]
