import asyncio
import base64
import logging
from typing import List, Dict, Optional
from io import BytesIO
from PIL import Image

from utils.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

class TableAnalyzer:
    def __init__(self, gemini_client: GeminiClient):
        self.gemini = gemini_client

    async def analyze_medical_table(self, image_data: bytes) -> List[Dict]:
        """
        Аналіз таблиці з медоглядами
        Повертає список словників: [{"name": "Прізвище", "medical": "М", "fluorography": "Ф", "gynecology": "Г", "vaccination": "В"}, ...]
        """
        prompt = """Проаналізуй цю таблицю з медичними оглядами. 
        Розпізнай прізвища працівників та позначки про необхідні огляди.
        
        Для кожного працівника визнач:
        - М (медогляд)
        - Ф (флюрографія)
        - Г (гінеколог) - тільки для жінок
        - В (щеплення)
        
        Формат відповіді (тільки JSON, без додаткового тексту):
        [
            {"name": "Прізвище", "medical": "так/ні", "fluorography": "так/ні", "gynecology": "так/ні", "vaccination": "так/ні"},
            ...
        ]
        
        Якщо позначка є - став "так", якщо немає - "ні".
        Відповідай тільки JSON масивом.
        """
        
        try:
            # Конвертуємо зображення в base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            response = await self.gemini.generate_with_image(prompt, image_base64, "image/jpeg")
            
            # Очищаємо відповідь від можливих маркерів коду
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:]
            if response.startswith('```'):
                response = response[3:]
            if response.endswith('```'):
                response = response[:-3]
            
            import json
            result = json.loads(response.strip())
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing medical table: {e}")
            return []

    async def analyze_sunday_work_table(self, image_data: bytes) -> List[Dict]:
        """
        Аналіз таблиці з роботою в неділю
        Повертає список словників: [{"name": "Прізвище", "need_to_work": "так/ні"}, ...]
        """
        prompt = """Проаналізуй цю таблицю з графіком роботи в неділю.
        Розпізнай прізвища працівників та позначки хто працює в неділю.
        
        Формат відповіді (тільки JSON, без додаткового тексту):
        [
            {"name": "Прізвище", "need_to_work": "так"},
            {"name": "Прізвище", "need_to_work": "ні"},
            ...
        ]
        
        Якщо працівник позначений як той, хто працює - став "так", якщо ні - "ні".
        Відповідай тільки JSON масивом.
        """
        
        try:
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            response = await self.gemini.generate_with_image(prompt, image_base64, "image/jpeg")
            
            # Очищаємо відповідь
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:]
            if response.startswith('```'):
                response = response[3:]
            if response.endswith('```'):
                response = response[:-3]
            
            import json
            result = json.loads(response.strip())
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing sunday work table: {e}")
            return []

    def format_medical_message(self, employee_data: Dict) -> str:
        """
        Форматує повідомлення про медогляд для конкретного працівника
        """
        needed = []
        
        if employee_data.get('medical') == 'так':
            needed.append("медогляд")
        if employee_data.get('fluorography') == 'так':
            needed.append("флюрографію")
        if employee_data.get('gynecology') == 'так':
            needed.append("гінеколога")
        if employee_data.get('vaccination') == 'так':
            needed.append("щеплення")
        
        if not needed:
            return None
        
        needed_text = ", ".join(needed)
        return f"⚠️ Шановний(а) {employee_data['name']}! Нагадуємо, що Вам необхідно пройти: {needed_text}. Будь ласка, зверніться до медпункту."

    def format_sunday_message(self, employee_name: str) -> str:
        """
        Форматує повідомлення про роботу в неділю
        """
        return f"⚠️ Шановний(а) {employee_name}! Нагадуємо, що Ви заплановані на роботу в неділю. Будь ласка, підтвердьте свою присутність."
