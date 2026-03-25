import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.errors import UserNotParticipant, ChatAdminRequired

# Импорты
from config import Config
from database import db
from keyboards import Keyboards
from handlers.start import start_command
from handlers.user import (
    handle_profile, handle_referral, handle_help,
    handle_games, handle_game_selection, handle_cheat_selection,
    handle_back_to_games, handle_back_to_main
)
from handlers.admin import (
    handle_admin_panel, handle_file_upload, 
    waiting_for_file, cancel_upload
)
from handlers.broadcast import (
    handle_broadcast_message, cancel_broadcast,
    waiting_for_broadcast
)

logger = logging.getLogger(__name__)

# Создаем клиент
app = Client(
    "plutonium_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    parse_mode="HTML"
)


# --- ФУНКЦИЯ ПРОВЕРКИ ПОДПИСКИ ---
async def check_subscription(user_id: int) -> bool:
    """Проверка подписки на канал"""
    if not Config.CHANNEL_ID:
        return True
    
    try:
        member = await app.get_chat_member(Config.CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except UserNotParticipant:
        return False
    except ChatAdminRequired:
        logger.warning("Бот не админ в канале, проверка отключена")
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return True


# --- ОБРАБОТЧИКИ ---
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    await start_command(client, message)


@app.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if waiting_for_file.get(user_id):
        cancel_upload(user_id)
        await message.reply("✅ Загрузка отменена")
    elif waiting_for_broadcast.get(user_id):
        cancel_broadcast(user_id)
        await message.reply("✅ Рассылка отменена")
    else:
        await message.reply("❌ Нет активных операций")


@app.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    """Обработка callback кнопок"""
    data = callback.data
    user_id = callback.from_user.id
    
    if data == "check_sub":
        subscribed = await check_subscription(user_id)
        
        if subscribed:
            keyboard = Keyboards.admin() if db.is_admin(user_id) else Keyboards.main()
            user_data = db.get_user(user_id)
            invites = user_data['total_invites'] if user_data else 0
            
            await callback.message.edit_text(
                f"🎮 **Plutonium Cheats**\n\n"
                f"✅ Подписка подтверждена!\n\n"
                f"👋 Добро пожаловать, {callback.from_user.first_name}!\n"
                f"👥 Приглашений: {invites}\n\n"
                f"Используй кнопки ниже:",
                reply_markup=keyboard
            )
        else:
            await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)


@app.on_message(filters.text & filters.private)
async def text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text
    
    # Если идет рассылка - обрабатываем отдельно
    if waiting_for_broadcast.get(user_id, False):
        await handle_broadcast_message(client, message)
        return
    
    # Проверка подписки
    subscribed = await check_subscription(user_id)
    if not subscribed:
        await message.reply(
            "🔒 **Доступ ограничен!**\n\n"
            "Подпишись на канал, чтобы пользоваться ботом.",
            reply_markup=Keyboards.subscribe()
        )
        return
    
    # Обновляем активность
    db.update_activity(user_id)
    
    # --- Обработка кнопок ---
    
    # Главное меню
    if text == "🔙 Главное меню":
        await handle_back_to_main(client, message)
        return
    
    if text == "🔙 Назад к играм":
        await handle_back_to_games(client, message)
        return
    
    # Пользовательские кнопки
    if text == "👤 Профиль":
        await handle_profile(client, message)
    
    elif text == "🔗 Рефералка":
        await handle_referral(client, message)
    
    elif text == "❓ Помощь":
        await handle_help(client, message)
    
    elif text == "🎮 Игры":
        await handle_games(client, message)
    
    # Выбор игры
    elif text.startswith("🎮 "):
        game = text[3:]
        await handle_game_selection(client, message, game)
    
    # Выбор чита
    elif text.startswith("📄 "):
        cheat_name = text[3:]
        await handle_cheat_selection(client, message, cheat_name)
    
    # Админ-панель
    elif text in ["📁 Добавить чит", "📋 Список читов", "👥 Пользователи", 
                  "📢 Рассылка", "📊 Статистика", "🧹 Очистка", 
                  "💾 Бэкап", "🔙 Главное меню"]:
        await handle_admin_panel(client, message, text)
    
    else:
        # Поиск по игре
        games = db.get_all_games()
        for g in games:
            if text.lower() in g['game'].lower():
                await handle_game_selection(client, message, g['game'])
                return
        
        await message.reply("❓ Не понял команду. Используй кнопки.")


@app.on_message((filters.document | filters.video | filters.photo) & filters.private)
async def file_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Если ожидаем файл от админа
    if waiting_for_file.get(user_id, False):
        await handle_file_upload(client, message)
    else:
        await message.reply("📤 Отправь /start для начала работы.")


# --- ЗАПУСК ---
if __name__ == "__main__":
    logger.info("🚀 Запуск Plutonium Bot...")
    logger.info(f"👑 Владелец: {Config.OWNER_ID}")
    logger.info(f"📢 Канал: {Config.CHANNEL_ID}")
    logger.info(f"💾 База: {Config.DB_PATH}")
    
    try:
        app.run()
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
