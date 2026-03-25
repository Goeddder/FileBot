import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Config:
    """Конфигурация бота с значениями по умолчанию"""
    
    # Telegram API - берем из переменных или используем значения по умолчанию
    API_ID = int(os.environ.get("API_ID", 39522849))
    API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
    
    # Владелец
    OWNER_ID = int(os.environ.get("OWNER_ID", 1471307057))
    
    # Каналы (опциональные)
    CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/OfficialPlutonium")
    CHANNEL_ID = os.environ.get("CHANNEL_ID", "@OfficialPlutonium")
    STORAGE_CHANNEL = os.environ.get("STORAGE_CHANNEL", "@IllyaTelegram")
    
    # База данных
    DB_PATH = "files.db"
    
    @classmethod
    def validate(cls):
        """Проверка переменных с выводом предупреждений, но без падения"""
        warnings = []
        
        if not cls.API_ID:
            warnings.append("API_ID не установлен, используется значение по умолчанию")
        if not cls.API_HASH:
            warnings.append("API_HASH не установлен, используется значение по умолчанию")
        if not cls.BOT_TOKEN:
            warnings.append("BOT_TOKEN не установлен, используется значение по умолчанию")
        if not cls.OWNER_ID:
            warnings.append("OWNER_ID не установлен, используется значение по умолчанию")
        
        if warnings:
            for w in warnings:
                logger.warning(w)
        else:
            logger.info("✅ Все переменные окружения загружены")
        
        return True

# Проверяем при импорте
Config.validate()
logger.info(f"🚀 Бот запускается с API_ID: {Config.API_ID}")
logger.info(f"👑 Владелец: {Config.OWNER_ID}")
