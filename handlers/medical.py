from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from io import BytesIO
from PIL import Image

from database import Database
from utils.table_analyzer import TableAnalyzer
from utils.sms_fly_client import SMSFlyClient
from config import SMS_FLY_API_KEY, SMS_FLY_SENDER

logger = logging.getLogger(__name__)

router = Router()

class MedicalStates(StatesGroup):
    waiting_for_photo = State()
    confirming_send = State()

def setup_medical_handler(dp, db: Database, analyzer: TableAnalyzer, sms_client: SMSFlyClient):
    """Налаштування обробника медпункту"""
    router.db = db
    router.analyzer = analyzer
    router.sms_client = sms_client
    dp.include_router(router)

@router.message(F.text == "🏥 Медпункт")
async def medical_start(message: types.Message, state: FSMContext):
    """Почати роботу з медпунктом"""
    await message.answer(
        "🏥 **Медичний огляд працівників**\n\n"
        "Сфотографуйте таблицю з графіком медоглядів.\n"
        "Я розпізнаю прізвища та необхідні процедури.\n\n"
        "📸 *Натисніть на скріпку та оберіть камерою*",
        parse_mode="Markdown"
    )
    await state.set_state(MedicalStates.waiting_for_photo)

@router.message(MedicalStates.waiting_for_photo, F.photo)
async def process_medical_table(message: types.Message, state: FSMContext, bot: Bot):
    """Обробити фото таблиці з медоглядами"""
    wait_msg = await message.answer("📊 **Аналізую таблицю...**", parse_mode="Markdown")
    
    try:
        # Отримуємо фото
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        
        # Аналізуємо таблицю
        employees_data = await router.analyzer.analyze_medical_table(file_bytes.read())
        
        if not employees_data:
            await wait_msg.edit_text(
                "❌ **Не вдалося розпізнати таблицю.**\n"
                "Спробуйте сфотографувати чіткіше або переконайтеся, що таблиця добре видна.",
                parse_mode="Markdown"
            )
            await state.clear()
            return
        
        # Формуємо результат
        result_text = "📋 **Результат аналізу:**\n\n"
        
        # Фільтруємо тих, кому потрібні огляди
        employees_with_needs = []
        
        for emp in employees_data:
            needs = []
            if emp.get('medical') == 'так':
                needs.append("М")
            if emp.get('fluorography') == 'так':
                needs.append("Ф")
            if emp.get('gynecology') == 'так':
                needs.append("Г")
            if emp.get('vaccination') == 'так':
                needs.append("В")
            
            if needs:
                result_text += f"• {emp['name']}: {', '.join(needs)}\n"
                employees_with_needs.append({
                    "name": emp['name'],
                    "needs": needs,
                    "full_data": emp
                })
            else:
                result_text += f"• {emp['name']}: ✅ всі огляди пройдено\n"
        
        # Зберігаємо дані в стані
        await state.update_data(employees_data=employees_with_needs)
        
        # Додаємо кнопки для відправки SMS
        kb = InlineKeyboardBuilder()
        kb.button(text="✉️ Відправити SMS нагадування", callback_data="send_medical_sms")
        kb.button(text="❌ Скасувати", callback_data="cancel_medical")
        kb.adjust(1)
        
        await wait_msg.edit_text(
            result_text + "\n\n⚠️ **Увага!**\n"
            "Працівникам, які мають позначки М, Ф, Г, В буде відправлено SMS нагадування.\n\n"
            "Бажаєте відправити?",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Medical table processing error: {e}")
        await wait_msg.edit_text(
            "❌ **Помилка при обробці фото.**\n"
            "Спробуйте ще раз або зверніться до адміністратора.",
            parse_mode="Markdown"
        )
        await state.clear()

@router.callback_query(F.data == "send_medical_sms")
async def send_medical_sms(callback: types.CallbackQuery, state: FSMContext):
    """Відправити SMS нагадування про медогляди"""
    data = await state.get_data()
    employees_data = data.get('employees_data', [])
    
    if not employees_data:
        await callback.message.edit_text(
            "❌ **Немає даних для відправки.**\n"
            "Спробуйте ще раз з фото.",
            parse_mode="Markdown"
        )
        await state.clear()
        return
    
    await callback.message.edit_text(
        f"📤 **Відправляю SMS {len(employees_data)} працівникам...**\n"
        "Будь ласка, зачекайте.",
        parse_mode="Markdown"
    )
    
    # Отримуємо номери телефонів з бази даних
    # Тут потрібно мати таблицю з телефонами працівників
    # Для прикладу, додамо тимчасову логіку
    results = []
    
    for emp in employees_data:
        # Отримуємо номер телефону з БД (потрібно реалізувати)
        phone = await get_employee_phone(router.db, emp['name'])
        
        if phone:
            # Форматуємо повідомлення
            message_text = router.analyzer.format_medical_message(emp['full_data'])
            if message_text:
                result = await router.sms_client.send_sms(phone, message_text)
                results.append({"name": emp['name'], "phone": phone, "result": result})
    
    # Формуємо звіт
    report = "📊 **Звіт про відправку SMS:**\n\n"
    success_count = sum(1 for r in results if r['result']['success'])
    
    report += f"✅ Успішно: {success_count}\n"
    report += f"❌ Помилок: {len(results) - success_count}\n\n"
    
    if results:
        report += "**Деталі:**\n"
        for r in results[:10]:  # Показуємо перші 10
            status = "✅" if r['result']['success'] else "❌"
            report += f"{status} {r['name']} ({r['phone']})\n"
    
    await callback.message.edit_text(report, parse_mode="Markdown")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_medical")
async def cancel_medical(callback: types.CallbackQuery, state: FSMContext):
    """Скасувати відправку SMS"""
    await callback.message.edit_text(
        "✅ **Операцію скасовано.**\n"
        "Дані не було відправлено.",
        parse_mode="Markdown"
    )
    await state.clear()
    await callback.answer()

async def get_employee_phone(db: Database, name: str) -> str:
    """
    Отримати номер телефону працівника з БД
    Потрібно додати таблицю employee_phones
    """
    # Тимчасово повертаємо тестовий номер
    # В реальності потрібно реалізувати пошук в БД
    return None
