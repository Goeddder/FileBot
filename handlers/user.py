import logging
from pyrogram import Client
from pyrogram.types import Message
from database import db
from keyboards import Keyboards
from utils.helpers import check_subscription
from config import Config

logger = logging.getLogger(__name__)

async def handle_profile(client: Client, message: Message):
    """Профиль пользователя"""
    user_data = db.get_user(message.from_user.id)
    invites = user_data['total_invites'] if user_data else 0
    
    await message.reply(
        f"👤 **Твой профиль**\n\n"
        f"🆔 ID: `{message.from_user.id}`\n"
        f"👥 Приглашений: {invites}\n\n"
        f"🔗 Приглашай друзей и получай больше читов!",
        reply_markup=Keyboards.main()
    )


async def handle_referral(client: Client, message: Message):
    """Реферальная ссылка"""
    bot = await client.get_me()
    ref_link = f"https://t.me/{bot.username}?start=ref_{message.from_user.id}"
    
    await message.reply(
        f"🔗 **Твоя реферальная ссылка:**\n\n"
        f"`{ref_link}`\n\n"
        f"📢 Отправь эту ссылку друзьям!\n"
        f"За каждого приглашенного ты получаешь +1 к счету.",
        reply_markup=Keyboards.main()
    )


async def handle_help(client: Client, message: Message):
    """Помощь"""
    await message.reply(
        f"📋 **Как пользоваться ботом:**\n\n"
        f"1️⃣ Нажми «🎮 Игры»\n"
        f"2️⃣ Выбери игру\n"
        f"3️⃣ Нажми на название чита\n"
        f"4️⃣ Файл автоматически отправится\n\n"
        f"🔗 **Рефералка:**\n"
        f"• Отправляй свою ссылку друзьям\n"
        f"• За каждого приглашенного получаешь +1\n\n"
        f"📌 Для админов есть дополнительные команды.",
        reply_markup=Keyboards.main()
    )


async def handle_games(client: Client, message: Message):
    """Список игр"""
    games = db.get_all_games()
    
    if not games:
        await message.reply("📭 Пока нет доступных читов.", reply_markup=Keyboards.main())
        return
    
    await message.reply(
        "🎮 **Доступные игры:**\n\nВыбери игру:",
        reply_markup=Keyboards.games(games)
    )


async def handle_game_selection(client: Client, message: Message, game: str):
    """Выбор игры"""
    files = db.get_files_by_game(game)
    
    if not files:
        await message.reply(f"❌ Для игры {game} пока нет читов.", reply_markup=Keyboards.back_to_games())
        return
    
    await message.reply(
        f"🎮 **{game}**\n\nВыбери чит:",
        reply_markup=Keyboards.cheats(files)
    )


async def handle_cheat_selection(client: Client, message: Message, cheat_name: str):
    """Выбор чита"""
    file_data = db.get_file_by_name(cheat_name)
    
    if not file_data:
        await message.reply(f"❌ Чит '{cheat_name}' не найден.")
        return
    
    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=Config.STORAGE_CHANNEL,
            message_id=file_data['remote_msg_id']
        )
        await message.reply(f"✅ {file_data['name']} отправлен!", reply_markup=Keyboards.back_to_games())
    except Exception as e:
        logger.error(f"Send file error: {e}")
        await message.reply(f"❌ Ошибка загрузки файла.", reply_markup=Keyboards.back_to_games())
