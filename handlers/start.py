import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from database import db
from keyboards import Keyboards
from utils.helpers import check_subscription
from config import Config

logger = logging.getLogger(__name__)

async def start_command(client: Client, message: Message):
    """Обработчик команды /start"""
    user = message.from_user
    inviter_id = None
    
    # Обработка реферальной ссылки
    if len(message.command) > 1:
        ref = message.command[1]
        if ref.startswith("ref_"):
            try:
                inviter_id = int(ref.split("_")[1])
                if inviter_id == user.id:
                    inviter_id = None
            except:
                pass
    
    # Сохраняем пользователя
    db.save_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        inviter_id=inviter_id
    )
    
    # Проверяем подписку
    subscribed = await check_subscription(client, user.id)
    
    if not subscribed:
        await message.reply(
            f"🔒 **Доступ ограничен!**\n\n"
            f"👋 Привет, {user.first_name}!\n\n"
            f"Для доступа к читам подпишись на канал.",
            reply_markup=Keyboards.subscribe()
        )
        return
    
    # Показываем главное меню
    keyboard = Keyboards.admin() if db.is_admin(user.id) else Keyboards.main()
    
    user_data = db.get_user(user.id)
    invites = user_data['total_invites'] if user_data else 0
    
    await message.reply(
        f"🎮 **Plutonium Cheats**\n\n"
        f"👋 Добро пожаловать, {user.first_name}!\n"
        f"👥 Приглашений: {invites}\n\n"
        f"Используй кнопки ниже:",
        reply_markup=keyboard
    )
