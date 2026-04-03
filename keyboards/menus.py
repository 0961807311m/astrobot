from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import KeyboardButton, InlineKeyboardButton

def main_menu():
    """Головне меню"""
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📋 Завдання на зміну"),
        KeyboardButton(text="📋 Чек-лист зміни")
    )
    builder.row(
        KeyboardButton(text="🚍 Маршрути"),
        KeyboardButton(text="✨ Порада дня")
    )
    builder.row(
        KeyboardButton(text="⚙️ Зміна"),
        KeyboardButton(text="🎂 Дні народження")
    )
    builder.row(
        KeyboardButton(text="🏥 Медпункт"),
        KeyboardButton(text="📅 Робота в неділю")
    )
    return builder.as_markup(resize_keyboard=True)
