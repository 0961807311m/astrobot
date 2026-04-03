from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

from database import Database
from utils.table_analyzer import TableAnalyzer
from utils.sms_fly_client import SMSFlyClient

logger = logging.getLogger(__name__)

router = Router()

class SundayWorkStates(StatesGroup):
    waiting_for_photo = State()
    confirming_send = State()

def setup_sunday_work_handler(dp, db: Database, analyzer: TableAnalyzer, sms_client: SMSFlyClient):
    """Налаштування обробника роботи в неділю"""
    router.db = db
    router.analyzer = analyzer
    router.sms_client = sms_client
    dp.include_router(router)

@router.message(F.text == "📅 Робота в неділю")
async def sunday_work_start(message: types.Message, state: FSMContext):
    """Почати роботу з графіком на неділю"""
    await message.answer(
        "📅 **Графік роботи в неділю**\n\n"
        "Сфотографуйте таблицю з графіком роботи на неділю.\n"
        "Я розпізнаю прізвища працівників, які мають працювати.\n\n"
        "📸 *Натисніть на скріпку та оберіть камерою*",
        parse_mode="Markdown"
    )
    await state.set_state(SundayWorkStates.waiting_for_photo)

@router.message(SundayWorkStates.waiting_for_photo, F.photo)
async def process_sunday_table(message: types.Message, state: FSMContext, bot: Bot):
    """Обробити фото таблиці з графіком на неділю"""
    wait_msg = await message.answer("📊 **Аналізую таблицю...**", parse_mode="Markdown")
    
    try:
        # Отримуємо фото
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        
        # Аналізуємо таблицю
        employees_data = await router.analyzer.analyze_sunday_work_table(file_bytes.read())
        
        if not employees_data:
            await wait_msg.edit_text(
                "❌ **Не вдалося розпізнати таблицю.**\n"
                "Спробуйте сфотографувати чіткіше або переконайтеся, що таблиця добре видна.",
                parse_mode="Markdown"
            )
            await state.clear()
            return
        
        # Фільтруємо тих, хто працює
        workers = [emp for emp in employees_data if emp.get('need_to_work') == 'так']
        
        if not workers:
            await wait_msg.edit_text(
                "📭 **Ніхто не працює в неділю**\n"
                "За графіком немає працівників на неділю.",
                parse_mode="Markdown"
            )
            await state.clear()
            return
        
        # Формуємо результат
        result_text = "📋 **Працівники, які працюють в неділю:**\n\n"
        for worker in workers:
            result_text += f"• {worker['name']}\n"
        
        # Зберігаємо дані в стані
        await state.update_data(workers=workers)
        
        # Додаємо кнопки для відправки SMS
        kb = InlineKeyboardBuilder()
        kb.button(text="✉️ Відправити SMS нагадування", callback_data="send_sunday_sms")
        kb.button(text="❌ Скасувати", callback_data="cancel_sunday")
        kb.adjust(1)
        
        await wait_msg.edit_text(
            result_text + "\n\n⚠️ **Увага!**\n"
            f"Цим працівникам буде відправлено SMS нагадування про роботу в неділю ({len(workers)} осіб).\n\n"
            "Бажаєте відправити?",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Sunday work table processing error: {e}")
        await wait_msg.edit_text(
            "❌ **Помилка при обробці фото.**\n"
            "Спробуйте ще раз або зверніться до адміністратора.",
            parse_mode="Markdown"
        )
        await state.clear()

@router.callback_query(F.data == "send_sunday_sms")
async def send_sunday_sms(callback: types.CallbackQuery, state: FSMContext):
    """Відправити SMS нагадування про роботу в неділю"""
    data = await state.get_data()
    workers = data.get('workers', [])
    
    if not workers:
        await callback.message.edit_text(
            "❌ **Немає даних для відправки.**\n"
            "Спробуйте ще раз з фото.",
            parse_mode="Markdown"
        )
        await state.clear()
        return
    
    await callback.message.edit_text(
        f"📤 **Відправляю SMS {len(workers)} працівникам...**\n"
        "Будь ласка, зачекайте.",
        parse_mode="Markdown"
    )
    
    results = []
    
    for worker in workers:
        # Отримуємо номер телефону з БД
        phone = await get_employee_phone(router.db, worker['name'])
        
        if phone:
            # Форматуємо повідомлення
            message_text = router.analyzer.format_sunday_message(worker['name'])
            result = await router.sms_client.send_sms(phone, message_text)
            results.append({"name": worker['name'], "phone": phone, "result": result})
    
    # Формуємо звіт
    report = "📊 **Звіт про відправку SMS:**\n\n"
    success_count = sum(1 for r in results if r['result']['success'])
    
    report += f"✅ Успішно: {success_count}\n"
    report += f"❌ Помилок: {len(results) - success_count}\n\n"
    
    if results:
        report += "**Деталі:**\n"
        for r in results[:10]:
            status = "✅" if r['result']['success'] else "❌"
            report += f"{status} {r['name']} ({r['phone']})\n"
    
    await callback.message.edit_text(report, parse_mode="Markdown")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_sunday")
async def cancel_sunday(callback: types.CallbackQuery, state: FSMContext):
    """Скасувати відправку SMS"""
    await callback.message.edit_text(
        "✅ **Операцію скасовано.**\n"
        "Дані не було відправлено.",
        parse_mode="Markdown"
    )
    await state.clear()
    await callback.answer()
