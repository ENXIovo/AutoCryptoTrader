import time
import logging
from .config import settings
from .services.telegram_service import TelegramService
from .services.redis_service import RedisService

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("alert_service")

class AlertManager:
    def __init__(self):
        self.redis_service = RedisService()
        self.telegram_service = TelegramService()

    def format_alert_message(self, data: dict, score: float) -> str:
        summary = data.get("summary", "No summary")
        source = data.get("source", "Unknown")
        importance = data.get("importance", "0")
        
        try:
            imp_val = float(importance)
            stars = "⭐" * int(imp_val * 5)
        except (ValueError, TypeError):
            stars = ""
            
        return (
            f"🚨 **News Alert** {stars}\n\n"
            f"**Summary:** {summary}\n"
            f"**Source:** {source}\n"
            f"**Score:** {score:.2f}\n"
        )

    def process_cycle(self):
        """Execute one cycle of checking and alerting."""
        items = self.redis_service.get_high_score_items(settings.ALERT_THRESHOLD)
        
        for key, score in items:
            if self.redis_service.is_alert_sent(key):
                continue
                
            data = self.redis_service.get_news_details(key)
            if not data:
                logger.warning(f"Data missing for key {key}")
                continue
                
            msg = self.format_alert_message(data, score)
            
            logger.info(f"Sending alert for {key} (score={score})")
            success = self.telegram_service.send_alert(msg)
            
            if success:
                self.redis_service.mark_alert_as_sent(key)
                self.redis_service.add_to_history(key, score, data.get("summary", ""))

    def run(self):
        logger.info("Starting Alert Service...")
        logger.info(f"Threshold: {settings.ALERT_THRESHOLD}")
        
        while True:
            try:
                self.process_cycle()
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
            
            time.sleep(settings.CHECK_INTERVAL)

if __name__ == "__main__":
    manager = AlertManager()
    manager.run()

