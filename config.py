import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Config:
    """Конфигурация бота"""
    
    # Telegram API
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    
    # Владелец
    OWNER_ID = int(os.environ.get("OWNER_ID", 0))
    
    # Каналы
    CHANNEL_URL = os.environ.get("CHANNEL_URL", "")
    CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
    STORAGE_CHANNEL = os.environ.get("STORAGE_CHANNEL", "")
    
    # База данных
    DB_PATH = "files.db"
    
    @classmethod
    def validate(cls):
        """Проверка обязательных переменных"""
        errors = []
        if not cls.API_ID:
            errors.append("API_ID")
        if not cls.API_HASH:
            errors.append("API_HASH")
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN")
        if not cls.OWNER_ID:
            errors.append("OWNER_ID")
        
        if errors:
            raise ValueError(f"Missing required env: {', '.join(errors)}")
        
        logger.info("✅ Конфигурация загружена")
        return True

# Проверяем при импорте
Config.validate()
