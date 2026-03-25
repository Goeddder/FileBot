import asyncio
import logging
from pyrogram import Client
from pyrogram.types import Message
from database import db
from keyboards import Keyboards

logger = logging.getLogger(__name__)

waiting_for_broadcast = {}


async def handle_broadcast_message(client: Client, message: Message):
    """Обработка сообщения для рассылки"""
    user_id = message.from_user.id
    
    if not waiting_for_broadcast.get(user_id, False):
        return
    
    if not db.is_admin(user_id):
        waiting_for_broadcast[user_id] = False
        return
    
    waiting_for_broadcast[user_id] = False
    
    users = db.get_all_users()
    if not users:
        await message.reply("❌ Нет пользователей для рассылки")
        return
    
    status = await message.reply(f"🚀 Рассылка на {len(users)} пользователей...")
    
    sent = 0
    failed = 0
    
    for i, user in enumerate(users):
        try:
            await message.copy(user['user_id'])
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed to {user['user_id']}: {e}")
        
        if (i + 1) % 10 == 0:
            await status.edit_text(
                f"📨 Прогресс: {sent + failed}/{len(users)}\n"
                f"✅ Успешно: {sent}\n"
                f"❌ Ошибок: {failed}"
            )
            await asyncio.sleep(0.5)
    
    await status.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"✅ Успешно: {sent}\n"
        f"❌ Ошибок: {failed}"
    )


async def cancel_operation(client: Client, message: Message):
    """Отмена активной операции"""
    user_id = message.from_user.id
    
    from handlers.admin import waiting_for_file
    from handlers.broadcast import waiting_for_broadcast
    
    if waiting_for_file.get(user_id):
        waiting_for_file[user_id] = False
        await message.reply("✅ Загрузка отменена")
    elif waiting_for_broadcast.get(user_id):
        waiting_for_broadcast[user_id] = False
        await message.reply("✅ Рассылка отменена")
    else:
        await message.reply("❌ Нет активных операций")
