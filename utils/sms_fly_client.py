import aiohttp
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class SMSFlyClient:
    def __init__(self, api_key: str, sender: str = "YourBot", proxy: Optional[str] = None):
        self.api_key = api_key
        self.sender = sender
        self.proxy = proxy
        self.base_url = "https://api.smsfly.ua/api/v1"

    async def send_sms(self, phone: str, message: str) -> Dict:
        """
        Відправка SMS одному отримувачу
        """
        url = f"{self.base_url}/send"
        
        # Нормалізуємо номер телефону
        phone = self._normalize_phone(phone)
        
        payload = {
            "api_key": self.api_key,
            "to": phone,
            "from": self.sender,
            "text": message
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, proxy=self.proxy) as resp:
                    data = await resp.json()
                    
                    if resp.status == 200 and data.get("status") == "ok":
                        logger.info(f"SMS sent to {phone}: {data}")
                        return {"success": True, "data": data}
                    else:
                        logger.error(f"SMS send error: {data}")
                        return {"success": False, "error": data.get("error", "Unknown error")}
                        
            except Exception as e:
                logger.error(f"SMS send exception: {e}")
                return {"success": False, "error": str(e)}

    async def send_bulk_sms(self, recipients: List[Dict]) -> List[Dict]:
        """
        Відправка SMS багатьом отримувачам
        recipients = [{"phone": "+380...", "message": "..."}, ...]
        """
        results = []
        
        for recipient in recipients:
            result = await self.send_sms(recipient["phone"], recipient["message"])
            results.append({
                "phone": recipient["phone"],
                "success": result["success"],
                "error": result.get("error")
            })
            
            # Невелика затримка, щоб не перевантажувати API
            await asyncio.sleep(0.5)
        
        return results

    def _normalize_phone(self, phone: str) -> str:
        """
        Нормалізує номер телефону до формату +380XXXXXXXXX
        """
        # Видаляємо всі зайві символи
        phone = ''.join(filter(str.isdigit, phone))
        
        # Якщо номер починається з 0, додаємо +38
        if phone.startswith('0'):
            phone = '+38' + phone
        # Якщо номер починається з 380, додаємо +
        elif phone.startswith('380'):
            phone = '+' + phone
        # Якщо номер починається з 8, замінюємо на +38
        elif phone.startswith('8'):
            phone = '+38' + phone[1:]
        
        return phone
