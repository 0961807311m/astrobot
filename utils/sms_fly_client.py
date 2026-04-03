import aiohttp
import logging
from typing import Dict, Optional, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SMSFlyClient:
    def __init__(self, api_key: str, sender: str = "YourBot"):
        """
        Ініціалізація клієнта SMS Fly API v2.4
        
        :param api_key: API ключ з особистого кабінету
        :param sender: Ім'я відправника (має бути зареєстроване в системі)
        """
        self.api_key = api_key
        self.sender = sender
        # Ваш URL підключення
        self.base_url = "https://sms-fly.ua/api/v2/api.php"

    async def send_sms(self, phone: str, message: str, ttl: int = 60, flash: int = 0) -> Dict:
        """
        Відправка SMS повідомлення
        
        :param phone: Номер телефону в міжнародному форматі (без +), наприклад: 380501234567
        :param message: Текст повідомлення
        :param ttl: Термін життя в хвилинах (1-1440)
        :param flash: 0 - звичайне, 1 - flash повідомлення
        :return: Результат відправки
        """
        # Нормалізуємо номер - видаляємо всі символи, крім цифр
        phone = ''.join(filter(str.isdigit, phone))
        
        # Якщо номер починається з 0, додаємо 380
        if phone.startswith('0'):
            phone = '380' + phone[1:]
        # Якщо номер починається з 8, замінюємо на 380
        elif phone.startswith('8'):
            phone = '380' + phone[1:]
        # Якщо номер не починається з 380, додаємо 380
        elif not phone.startswith('380'):
            phone = '380' + phone
            
        # Перевіряємо довжину (має бути 12 цифр: 380 + 9 цифр)
        if len(phone) != 12:
            logger.warning(f"Номер {phone} має нестандартну довжину: {len(phone)} цифр")
        
        # Формуємо запит згідно документації API v2.4
        payload = {
            "auth": {
                "key": self.api_key
            },
            "action": "SENDMESSAGE",
            "data": {
                "recipient": phone,
                "channels": ["sms"],
                "sms": {
                    "source": self.sender,
                    "ttl": ttl,
                    "flash": flash,
                    "text": message
                }
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, json=payload, timeout=30) as resp:
                    # Перевіряємо HTTP статус
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # Перевіряємо success поле у відповіді
                        if data.get('success') == 1:
                            # Успішна відправка
                            result = {
                                "success": True,
                                "message_id": data.get('data', {}).get('messageID'),
                                "status": data.get('data', {}).get('sms', {}).get('status'),
                                "cost": data.get('data', {}).get('sms', {}).get('cost'),
                                "full_response": data
                            }
                            logger.info(f"SMS відправлено на {phone}, ID: {result['message_id']}")
                            return result
                        else:
                            # Помилка від API
                            error = data.get('error', {})
                            logger.error(f"API помилка: {error.get('code')} - {error.get('description')}")
                            return {
                                "success": False,
                                "error_code": error.get('code'),
                                "error_description": error.get('description'),
                                "full_response": data
                            }
                    else:
                        # HTTP помилка
                        logger.error(f"HTTP помилка: {resp.status}")
                        return {
                            "success": False,
                            "error": f"HTTP {resp.status}",
                            "http_status": resp.status
                        }
                        
            except Exception as e:
                logger.error(f"Помилка при відправці SMS: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }

    async def send_viber_message(self, phone: str, text: str, source: str = None, 
                                  ttl: int = 60, button_caption: str = None, 
                                  button_url: str = None, image_url: str = None) -> Dict:
        """
        Відправка Viber повідомлення
        
        :param phone: Номер телефону в міжнародному форматі (без +)
        :param text: Текст повідомлення (до 1000 символів)
        :param source: Ім'я відправника Viber
        :param ttl: Термін життя в хвилинах (1-1440)
        :param button_caption: Текст на кнопці (до 30 символів)
        :param button_url: URL для переходу по кнопці
        :param image_url: URL зображення для повідомлення
        """
        # Нормалізуємо номер
        phone = ''.join(filter(str.isdigit, phone))
        if phone.startswith('0'):
            phone = '380' + phone[1:]
        elif phone.startswith('8'):
            phone = '380' + phone[1:]
        elif not phone.startswith('380'):
            phone = '380' + phone
            
        # Формуємо Viber частину повідомлення
        viber_data = {
            "source": source or self.sender,
            "ttl": ttl,
            "text": text
        }
        
        # Додаємо кнопку, якщо вказана
        if button_caption and button_url:
            viber_data["button"] = {
                "caption": button_caption[:30],
                "url": button_url
            }
        
        # Додаємо зображення, якщо вказано
        if image_url:
            viber_data["image"] = image_url
        
        payload = {
            "auth": {
                "key": self.api_key
            },
            "action": "SENDMESSAGE",
            "data": {
                "recipient": phone,
                "channels": ["viber"],
                "viber": viber_data
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') == 1:
                            return {
                                "success": True,
                                "message_id": data.get('data', {}).get('messageID'),
                                "status": data.get('data', {}).get('viber', {}).get('status'),
                                "cost": data.get('data', {}).get('viber', {}).get('cost')
                            }
                        else:
                            error = data.get('error', {})
                            return {
                                "success": False,
                                "error_code": error.get('code'),
                                "error_description": error.get('description')
                            }
                    else:
                        return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def send_with_fallback(self, phone: str, text: str, 
                                  viber_source: str = None, 
                                  sms_source: str = None) -> Dict:
        """
        Відправка з fallback: спочатку Viber, якщо не доставлено - SMS
        """
        phone = ''.join(filter(str.isdigit, phone))
        if phone.startswith('0'):
            phone = '380' + phone[1:]
        elif not phone.startswith('380'):
            phone = '380' + phone
            
        payload = {
            "auth": {
                "key": self.api_key
            },
            "action": "SENDMESSAGE",
            "data": {
                "recipient": phone,
                "channels": ["viber", "sms"],
                "viber": {
                    "source": viber_source or self.sender,
                    "ttl": 60,
                    "text": text
                },
                "sms": {
                    "source": sms_source or self.sender,
                    "ttl": 60,
                    "flash": 0,
                    "text": text
                }
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') == 1:
                            return {
                                "success": True,
                                "message_id": data.get('data', {}).get('messageID'),
                                "viber_status": data.get('data', {}).get('viber', {}).get('status'),
                                "sms_status": data.get('data', {}).get('sms', {}).get('status'),
                                "cost": data.get('data', {}).get('viber', {}).get('cost', 0) + 
                                        data.get('data', {}).get('sms', {}).get('cost', 0)
                            }
                        else:
                            error = data.get('error', {})
                            return {
                                "success": False,
                                "error_code": error.get('code'),
                                "error_description": error.get('description')
                            }
                    else:
                        return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def get_balance(self) -> Dict:
        """Отримання балансу (тільки SMS)"""
        payload = {
            "auth": {
                "key": self.api_key
            },
            "action": "GETBALANCE",
            "data": {}
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') == 1:
                            return {
                                "success": True,
                                "balance": data.get('data', {}).get('balance', '0')
                            }
                        else:
                            error = data.get('error', {})
                            return {
                                "success": False,
                                "error_code": error.get('code'),
                                "error_description": error.get('description')
                            }
                    else:
                        return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def get_extended_balance(self) -> Dict:
        """Отримання розширеного балансу (SMS + Viber)"""
        payload = {
            "auth": {
                "key": self.api_key
            },
            "action": "GETBALANCEEXT",
            "data": {}
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') == 1:
                            balance_data = data.get('data', {}).get('balance', {})
                            return {
                                "success": True,
                                "sms_balance": balance_data.get('sms', '0'),
                                "viber_balance": balance_data.get('viber', '0')
                            }
                        else:
                            error = data.get('error', {})
                            return {
                                "success": False,
                                "error_code": error.get('code'),
                                "error_description": error.get('description')
                            }
                    else:
                        return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def get_message_status(self, message_id: str) -> Dict:
        """Отримання статусу повідомлення"""
        payload = {
            "auth": {
                "key": self.api_key
            },
            "action": "GETMESSAGESTATUS",
            "data": {
                "messageID": message_id
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') == 1:
                            return {
                                "success": True,
                                "message_id": data.get('data', {}).get('messageID'),
                                "viber_status": data.get('data', {}).get('viber', {}).get('status'),
                                "sms_status": data.get('data', {}).get('sms', {}).get('status')
                            }
                        else:
                            error = data.get('error', {})
                            return {
                                "success": False,
                                "error_code": error.get('code'),
                                "error_description": error.get('description')
                            }
                    else:
                        return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def get_senders(self, channels: List[str] = None) -> Dict:
        """Отримання списку доступних імен відправника"""
        if channels is None:
            channels = ["sms", "viber"]
            
        payload = {
            "auth": {
                "key": self.api_key
            },
            "action": "GETSOURCE",
            "data": {
                "channels": channels
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.base_url, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') == 1:
                            return {
                                "success": True,
                                "sms_senders": data.get('data', {}).get('sms', []),
                                "viber_senders": data.get('data', {}).get('viber', [])
                            }
                        else:
                            error = data.get('error', {})
                            return {
                                "success": False,
                                "error_code": error.get('code'),
                                "error_description": error.get('description')
                            }
                    else:
                        return {"success": False, "error": f"HTTP {resp.status}"}
            except Exception as e:
                return {"success": False, "error": str(e)}
