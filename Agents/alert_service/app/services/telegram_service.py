import logging
import requests
import re
import html
from ..config import settings

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def _markdown_to_html(self, text: str) -> str:
        """将 Markdown 格式转换为 HTML 格式"""
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        parts = re.split(r'(<[^>]+>)', text)
        return ''.join(part if part.startswith('<') and part.endswith('>') else html.escape(part) for part in parts)

    def send_alert(self, message: str) -> bool:
        """发送消息：先尝试 HTML 模式，失败则回退到纯文本"""
        html_message = self._markdown_to_html(message)
        try:
            resp = requests.post(
                self.base_url,
                json={"chat_id": self.chat_id, "text": html_message, "parse_mode": "HTML"},
                timeout=10
            )
            resp.raise_for_status()
            logger.info("Alert sent successfully via Telegram (HTML mode).")
            return True
        except requests.exceptions.HTTPError as e:
            if hasattr(e.response, 'status_code') and e.response.status_code == 400:
                try:
                    error_desc = e.response.json().get('description', 'Unknown error')
                    logger.warning(f"HTML parse failed, trying plain text: {error_desc}")
                except:
                    logger.warning("HTML parse failed, trying plain text")
            else:
                logger.warning(f"HTTP error: {e}")
        except Exception as e:
            logger.warning(f"Error: {e}")
        
        # 回退到纯文本
        try:
            resp = requests.post(
                self.base_url,
                json={"chat_id": self.chat_id, "text": message},
                timeout=10
            )
            resp.raise_for_status()
            logger.info("Alert sent successfully via Telegram (plain text mode).")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False
