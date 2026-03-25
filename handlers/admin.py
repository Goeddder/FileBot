import logging
import asyncio
import os
from datetime import datetime
from pyrogram import Client
from pyrogram.types import Message
from database import db
from keyboards import Keyboards
from utils.helpers import parse_file_caption, generate_hash
from config import Config

logger = logging.getLogger(__name__)

waiting_for_file = {}
waiting_for_broadcast = {}


async def handle_admin_panel(client: Client, message: Message, text: str):
    """Админ-панель"""
    user_id = message.from_user.id
    
    if not db.is_admin(user_id):
        return
    
    # Добавить чит
    if text == "📁 Добавить чит":
        waiting_for_file[user_id] = True
        await message.reply(
            "📤 **Добавление чита**\n\n"
            "1. Отправь файл\n"
            "2. В подписи укажи:\n"
            "`Название чита | Название игры`\n\n"
            "Пример: `Aimbot | CS2`\n\n"
            "Для отмены нажми /cancel",
            reply_markup=Keyboards.admin()
        )
        return
    
    # Список читов
    elif text == "📋 Список читов":
        files = db.get_all_files()
        
        if not files:
            await message.reply("📭 База читов пуста.", reply_markup=Keyboards.admin())
            return
        
        result = "📋 **Все читы:**\n\n"
        current_game = ""
        for f in files:
            if f['game'] != current_game:
                current_game = f['game']
                result += f"\n🎮 **{current_game}**\n"
            result += f"  • {f['name']}\n"
        
        await message.reply(result, reply_markup=Keyboards.admin())
        return
    
    # Пользователи
    elif text == "👥 Пользователи":
        users = db.fetch_all("SELECT user_id, first_name, total_invites FROM users ORDER BY total_invites DESC")
        
        result = "👥 **Пользователи:**\n\n"
        for i, u in enumerate(users[:30], 1):
            name = u['first_name'] or str(u['user_id'])
            result += f"{i}. {name} — пригл: {u['total_invites']}\n"
        result += f"\n📊 Всего: {len(users)}"
        
        await message.reply(result, reply_markup=Keyboards.admin())
        return
    
    # Рассылка
    elif text == "📢 Рассылка":
        waiting_for_broadcast[user_id] = True
        await message.reply(
            "📢 **Рассылка**\n\n"
            "Отправь сообщение для рассылки.\n"
            "Для отмены нажми /cancel",
            reply_markup=Keyboards.admin()
        )
        return
    
    # Статистика
    elif text == "📊 Статистика":
        stats = db.get_stats()
        await message.reply(
            f"📊 **Статистика**\n\n"
            f"📁 Читов: {stats['files']}\n"
            f"👥 Пользователей: {stats['users']}\n"
            f"🔗 Приглашений: {stats['invites']}",
            reply_markup=Keyboards.admin()
        )
        return
    
    # Очистка
    elif text == "🧹 Очистка":
        deleted = db.cleanup_inactive()
        await message.reply(f"🧹 Удалено неактивных: {deleted}", reply_markup=Keyboards.admin())
        return
    
    # Бэкап
    elif text == "💾 Бэкап":
        if os.path.exists(Config.DB_PATH):
            await message.reply_document(
                Config.DB_PATH,
                caption=f"📦 Бэкап от {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
        else:
            await message.reply("❌ Файл базы не найден")
        return
    
    # Главное меню
    elif text == "🔙 Главное меню":
        await message.reply(
            "🔙 Главное меню:",
            reply_markup=Keyboards.main()
        )
        return


async def handle_file_upload(client: Client, message: Message):
    """Обработка загрузки файла админом"""
    user_id = message.from_user.id
    
    if not waiting_for_file.get(user_id, False):
        return
    
    if not db.is_admin(user_id):
        waiting_for_file[user_id] = False
        return
    
    status = await message.reply("⏳ Сохраняю чит...")
    
    try:
        # Копируем в хранилище
        sent = await message.copy(Config.STORAGE_CHANNEL)
        
        # Парсим подпись
        name, game = parse_file_caption(message.caption)
        
        # Сохраняем в БД
        file_hash = generate_hash()
        file_type = "doc" if message.document else "video" if message.video else "photo"
        
        db.save_file(file_hash, sent.id, file_type, name, game, user_id)
        
        bot = await client.get_me()
        
        await status.edit_text(
            f"✅ **Чит добавлен!**\n\n"
            f"📄 {name}\n"
            f"🎮 {game}\n"
            f"🔗 `https://t.me/{bot.username}?start={file_hash}`"
        )
        
        waiting_for_file[user_id] = False
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await status.edit_text(f"❌ Ошибка: {str(e)}")
        waiting_for_file[user_id] = False
