from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

# Ваш список справ на початок зміни
CHECKLIST = [
    "Подати персонал до 16:50",
    "Склад ТМЦ",
    "Перевірити кількість тари та утіля",
    "Переглянути план 1.26 тари",
    "Черга авто логістика",
    "Заповнити журнали"

]

def get_checklist_kb(checked_items):
    keyboard = []
    for i, item in enumerate(CHECKLIST):
        # Якщо індекс є у списку checked_items, ставимо ✅, інакше ❌
        mark = "✅" if i in checked_items else "❌"
        keyboard.append([InlineKeyboardButton(
            text=f"{mark} {item}",
            callback_data=f"check_{i}_{checked_items}"
        )])

    # Кнопка завершення, з'являється тільки коли все відмічено
    if len(checked_items) == len(CHECKLIST):
        keyboard.append([InlineKeyboardButton(text="🏁 Завершити підготовку", callback_data="finish_shift")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.message(F.text == "🚀 Початок зміни")
async def start_shift(message: types.Message):
    await message.answer(
        "📋 <b>Чек-лист початку зміни:</b>\nВідмітьте виконані пункти:",
        reply_markup=get_checklist_kb([]),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("check_"))
async def toggle_check(callback: types.CallbackQuery):
    # Парсимо дані: індекс кнопки та список уже відмічених
    parts = callback.data.split("_")
    idx = int(parts[1])
    # Перетворюємо рядок списку назад у набір чисел
    checked_str = parts[2].strip("[]").replace(" ", "")
    checked = [int(x) for x in checked_str.split(",")] if checked_str else []

    if idx in checked:
        checked.remove(idx)
    else:
        checked.append(idx)

    # Оновлюємо повідомлення з новою клавіатурою
    await callback.message.edit_reply_markup(reply_markup=get_checklist_kb(checked))
    await callback.answer()

@router.callback_query(F.data == "finish_shift")
async def finish_shift(callback: types.CallbackQuery):
    await callback.message.edit_text("✅ <b>Всі пункти виконано! Гарної зміни!</b>", parse_mode="HTML")