import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from config import Config
from database import db
from keyboards import Keyboards
from utils.helpers import check_subscription
from handlers.start import start_command
from handlers.user import (
    handle_profile, handle_referral, handle_help,
    handle_games, handle_game_selection, handle_cheat_selection
)
from handlers.admin import handle_admin_panel, handle_file_upload, waiting_for_file
from handlers.broadcast import handle_broadcast_message, cancel_operation, waiting_for_broadcast

logger = logging.getLogger(__name__)

# Создаем клиент
app = Client(
    "plutonium_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    parse_mode="HTML"
)


@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    await start_command(client, message)


@app.on_message(filters.command("cancel") & filters.private)
async def cancel_handler(client: Client, message: Message):
    await cancel_operation(client, message)


@app.on_message(filters.text & filters.private)
async def text_handler(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text
    
    # Проверка подписки
    if not await check_subscription(client, user_id):
        await message.reply(
            "🔒 **Доступ ограничен!**\n\nПодпишись на канал.",
            reply_markup=Keyboards.subscribe()
        )
        return
    
    # Обновляем активность
    db.update_activity(user_id)
    
    # --- Пользовательские кнопки ---
    if text == "👤 Профиль":
        await handle_profile(client, message)
    
    elif text == "🔗 Рефералка":
        await handle_referral(client, message)
    
    elif text == "❓ Помощь":
        await handle_help(client, message)
    
    elif text == "🎮 Игры":
        await handle_games(client, message)
    
    elif text == "🔙 Назад к играм":
        await handle_games(client, message)
    
    # --- Выбор игры ---
    elif text.startswith("🎮 "):
        game = text[3:]
        await handle_game_selection(client, message, game)
    
    # --- Выбор чита ---
    elif text.startswith("📄 "):
        cheat_name = text[3:]
        await handle_cheat_selection(client, message, cheat_name)
    
    # --- Админ-панель ---
    elif text in ["📁 Добавить чит", "📋 Список читов", "👥 Пользователи", 
                  "📢 Рассылка", "📊 Статистика", "🧹 Очистка", 
                  "💾 Бэкап", "🔙 Главное меню"]:
        await handle_admin_panel(client, message, text)


@app.on_message((filters.document | filters.video | filters.photo) & filters.private)
async def file_handler(client: Client, message: Message):
    await handle_file_upload(client, message)


@app.on_message(filters.text & filters.private)
async def broadcast_handler(client: Client, message: Message):
    """Отдельный обработчик для рассылки"""
    user_id = message.from_user.id
    if waiting_for_broadcast.get(user_id, False):
        await handle_broadcast_message(client, message)


@app.on_callback_query()
async def callback_handler(client, callback):
    """Обработка callback кнопок"""
    data = callback.data
    
    if data == "check_sub":
        subscribed = await check_subscription(client, callback.from_user.id)
        
        if subscribed:
            keyboard = Keyboards.admin() if db.is_admin(callback.from_user.id) else Keyboards.main()
            user_data = db.get_user(callback.from_user.id)
            invites = user_data['total_invites'] if user_data else 0
            
            await callback.message.edit_text(
                f"🎮 **Plutonium Cheats**\n\n"
                f"✅ Подписка подтверждена!\n\n"
                f"👋 Добро пожаловать, {callback.from_user.first_name}!\n"
                f"👥 Приглашений: {invites}",
                reply_markup=keyboard
            )
        else:
            await callback.answer("❌ Вы еще не подписались!", show_alert=True)


if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    app.run()
