from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import database as db
import pandas as pd
import os

router = Router()

class BirthdayStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()
    waiting_for_search = State()

# КРУТА КЛАВІАТУРА ГОЛОВНОГО РОЗДІЛУ
def get_bd_kb():
    buttons = [
        [KeyboardButton(text="➕ Додати іменинника")],
        [KeyboardButton(text="🔍 Пошук / Видалення")],
        [KeyboardButton(text="🔙 Головне меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)

@router.message(F.text == "🎂 Дні народження")
async def start_birthdays(message: types.Message):
    text = (
        "<b>🎂 РОЗДІЛ: ДНІ НАРОДЖЕННЯ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Виберіть дію на клавіатурі нижче або\n"
        "<b>просто надішліть Excel-файл (.xlsx)</b>\n"
        "для масового імпорту даних. 📂"
    )
    await message.answer(text, reply_markup=get_bd_kb(), parse_mode="HTML")

# --- СТИЛІЗОВАНЕ ДОДАВАННЯ ---
@router.message(F.text == "➕ Додати іменинника")
async def add_bd_start(message: types.Message, state: FSMContext):
    await message.answer("👤 <b>Введіть Прізвище та Ім'я:</b>", parse_mode="HTML")
    await state.set_state(BirthdayStates.waiting_for_name)

@router.message(BirthdayStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📅 <b>Введіть дату (наприклад, 25.12):</b>", parse_mode="HTML")
    await state.set_state(BirthdayStates.waiting_for_date)

@router.message(BirthdayStates.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    db.add_birthday(message.from_user.id, user_data['name'], message.text)

    text = (
        "✅ <b>Успішно збережено!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 {user_data['name']}\n"
        f"📅 {message.text}"
    )
    await message.answer(text, reply_markup=get_bd_kb(), parse_mode="HTML")
    await state.clear()

# --- СТИЛІЗОВАНИЙ ПОШУК ТА ВИДАЛЕННЯ ---
@router.message(F.text == "🔍 Пошук / Видалення")
async def search_bd_start(message: types.Message, state: FSMContext):
    await message.answer("🔎 <b>Введіть прізвище для пошуку:</b>", parse_mode="HTML")
    await state.set_state(BirthdayStates.waiting_for_search)

@router.message(BirthdayStates.waiting_for_search)
async def process_search(message: types.Message, state: FSMContext):
    results = db.get_birthdays_by_name(message.from_user.id, message.text)
    if not results:
        await message.answer("❌ <b>Нікого не знайдено за цим запитом.</b>", parse_mode="HTML")
        await state.clear()
        return

    for entry_id, name, date in results:
        # Дизайн кнопок під кожним результатом
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Видалити", callback_data=f"del_{entry_id}"),
                InlineKeyboardButton(text="📝 Редагувати", callback_data=f"edit_{entry_id}")
            ],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
        ])

        res_text = (
            f"👤 <b>{name}</b>\n"
            f"📅 Дата народження: <code>{date}</code>"
        )
        await message.answer(res_text, reply_markup=kb, parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data.startswith("del_"))
async def delete_item(callback: types.CallbackQuery):
    entry_id = callback.data.split("_")[1]
    db.delete_birthday(entry_id)
    await callback.message.edit_text("🗑 <b>Запис назавжди видалено!</b>", parse_mode="HTML")

@router.callback_query(F.data == "cancel")
async def cancel_action(callback: types.CallbackQuery):
    await callback.message.edit_text("🆗 <b>Дію скасовано.</b>", parse_mode="HTML")