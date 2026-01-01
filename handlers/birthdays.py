from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database as db

router = Router()

class BirthdayStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()

@router.message(F.text == "🎂 Дні народження")
async def start_birthdays(message: types.Message):
    buttons = [[types.KeyboardButton(text="➕ Додати")], [types.KeyboardButton(text="🔙 Головне меню")]]
    kb = types.ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    await message.answer("🎂 <b>Розділ Днів Народження</b>", reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "➕ Додати")
async def add_bd_start(message: types.Message, state: FSMContext):
    await message.answer("👤 Введіть Ім'я:")
    await state.set_state(BirthdayStates.waiting_for_name)

@router.message(BirthdayStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📅 Введіть дату (25.12):")
    await state.set_state(BirthdayStates.waiting_for_date)

@router.message(BirthdayStates.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    data = await state.get_data()
    db.add_birthday(message.from_user.id, data['name'], message.text)
    await message.answer(f"✅ Збережено: {data['name']} - {message.text}")
    await state.clear()
