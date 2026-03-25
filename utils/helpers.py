import secrets
import logging
from typing import Tuple, Optional
from pyrogram import Client
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from config import Config

logger = logging.getLogger(__name__)

async def check_subscription(client: Client, user_id: int) -> bool:
    """Проверка подписки на канал"""
    if not Config.CHANNEL_ID:
        return True
    
    try:
        member = await client.get_chat_member(Config.CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except UserNotParticipant:
        return False
    except ChatAdminRequired:
        logger.warning("Bot is not admin in channel, skipping check")
        return True
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return True


def generate_hash() -> str:
    """Генерация уникального хеша"""
    return secrets.token_urlsafe(8)


def parse_file_caption(caption: str) -> Tuple[str, str]:
    """Парсинг подписи файла: Название | Игра"""
    if not caption:
        return "Без названия", "Без игры"
    
    if "|" in caption:
        parts = caption.split("|", 1)
        name = parts[0].strip()
        game = parts[1].strip()
        return name, game
    
    return caption.strip(), "Без игры"
