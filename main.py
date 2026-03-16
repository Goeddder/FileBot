import asyncio
import sqlite3
import secrets
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

# ========== НАСТРОЙКИ ==========
TOKEN = "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw"
ADMIN_ID = 1471307057
CHANNEL_URL = "https://t.me/OfficialPlutonium"
CHANNEL_ID = -1003607014773  # @OfficialPlutonium
STORAGE_CHANNEL_ID = -1003677537552  # @IllyaTelegram
# ================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- БАЗА ДАННЫХ ----------
def init_db():
    conn = sqlite3.connect('files.db')
    # ВАЖНО: храним message_id из канала, а не file_id
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            hash TEXT PRIMARY KEY,
            message_id INTEGER,
            file_name TEXT,
            caption TEXT,
            added_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

def save_user(user_id, username, first_name):
    conn = sqlite3.connect('files.db')
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    conn.close()

def save_file(file_hash, message_id, file_name, caption):
    conn = sqlite3.connect('files.db')
    conn.execute(
        "INSERT INTO files (hash, message_id, file_name, caption, added_at) VALUES (?, ?, ?, ?, ?)",
        (file_hash, message_id, file_name, caption, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    conn.close()
    logger.info(f"✅ Файл {file_hash} сохранен в БД (message_id: {message_id})")

def get_file(file_hash):
    conn = sqlite3.connect('files.db')
    row = conn.execute("SELECT message_id, file_name, caption FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()
    return row

def get_all_files():
    conn = sqlite3.connect('files.db')
    rows = conn.execute("SELECT hash, file_name, caption FROM files ORDER BY added_at DESC").fetchall()
    conn.close()
    return rows

def get_all_users():
    conn = sqlite3.connect('files.db')
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return rows

# ---------- ПРОВЕРКА ПОДПИСКИ ----------
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status not in ["left", "kicked"]
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

# ---------- КОМАНДА СТАРТ ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    save_user(user_id, username, first_name)
    logger.info(f"Пользователь {user_id} запустил бота")

    sub_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Канал Plutonium", url=CHANNEL_URL)]
    ])

    if len(message.text.split()) == 1:
        await message.answer(
            f"👋 Привет, {first_name}!\n\n"
            f"Я бот Plutonium. Перейди по ссылке, чтобы получить файл.",
            reply_markup=sub_button
        )
        return

    parts = message.text.split()
    if len(parts) > 1:
        file_hash = parts[1]
        
        if not await check_subscription(user_id):
            await message.answer(
                "⚠️ **Доступ закрыт!**\nСначала подпишись на канал.",
                reply_markup=sub_button
            )
            return

        file_info = get_file(file_hash)
        if not file_info:
            await message.answer("❌ Файл не найден или ссылка недействительна.")
            return

        message_id, file_name, caption = file_info
        
        try:
            # Пересылаем сообщение ИЗ КАНАЛА пользователю
            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=STORAGE_CHANNEL_ID,
                message_id=message_id,
                caption=f"📁 **{file_name}**\n\n{caption if caption else ''}",
                reply_markup=sub_button
            )
            logger.info(f"Файл {file_hash} (msg:{message_id}) отправлен пользователю {user_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки файла: {e}")
            await message.answer("❌ Ошибка при отправке файла. Сообщи админу.")

# ---------- ДОБАВЛЕНИЕ ФАЙЛА ----------
@dp.message(Command("addfile"))
async def cmd_addfile(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔️ Эта команда только для администратора.")
        return
    
    await message.answer(
        "📤 **Отправь файл** (документ, фото или видео).\n"
        "В описании можешь указать название и описание."
    )

@dp.message(F.document | F.video | F.photo)
async def handle_file(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if message.document:
        file_name = message.document.file_name or "документ"
    elif message.video:
        file_name = message.video.file_name or "видео"
    else:
        file_name = "фото"

    # Отправляем в канал-хранилище
    try:
        sent = await bot.send_document(
            chat_id=STORAGE_CHANNEL_ID,
            document=message.document or message.video or message.photo[-1].file_id,
            caption=f"📦 {file_name}"
        )
        # Сохраняем message_id из канала
        message_id = sent.message_id
        logger.info(f"Файл сохранен в канале, message_id: {message_id}")
    except Exception as e:
        logger.error(f"Ошибка сохранения в канал: {e}")
        await message.answer("❌ Не удалось сохранить файл в канал. Бот админ в канале?")
        return

    file_hash = secrets.token_urlsafe(8)
    caption = message.caption or ""
    save_file(file_hash, message_id, file_name, caption)

    bot_me = await bot.get_me()
    url = f"https://t.me/{bot_me.username}?start={file_hash}"
    
    await message.answer(
        f"✅ **Файл сохранён навечно!**\n\n"
        f"📁 **Название:** {file_name}\n"
        f"📝 **Описание:** {caption if caption else '—'}\n"
        f"🔗 **Ссылка:**\n`{url}`\n\n"
        f"💾 Файл сохранён в канале (ID: {message_id}) и будет работать всегда."
    )

# ---------- СПИСОК ФАЙЛОВ ----------
@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    files = get_all_files()
    if not files:
        await message.answer("📭 Нет файлов в базе.")
        return

    bot_me = await bot.get_me()
    text = "📂 **Все файлы:**\n\n"
    
    for file_hash, file_name, caption in files:
        url = f"https://t.me/{bot_me.username}?start={file_hash}"
        text += f"📁 **{file_name}**\n"
        if caption:
            text += f"📝 {caption[:50]}{'...' if len(caption) > 50 else ''}\n"
        text += f"🔗 `{url}`\n\n"
        
        if len(text) > 3500:
            await message.answer(text)
            text = "📂 **Продолжение:**\n\n"
    
    if text:
        await message.answer(text)

# ---------- РАССЫЛКА ----------
@dp.message(Command("send"))
async def cmd_send(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not message.reply_to_message:
        await message.answer("❌ Ответь этой командой на сообщение для рассылки.")
        return

    users = get_all_users()
    if not users:
        await message.answer("📭 Нет пользователей в базе.")
        return

    status_msg = await message.answer(f"🚀 Рассылка {len(users)} пользователям...")
    
    success = 0
    failed = 0
    
    for i, (user_id,) in enumerate(users, 1):
        try:
            await message.reply_to_message.copy(chat_id=user_id)
            success += 1
        except TelegramForbiddenError:
            failed += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await message.reply_to_message.copy(chat_id=user_id)
                success += 1
            except:
                failed += 1
        except Exception as e:
            logger.error(f"Ошибка отправки {user_id}: {e}")
            failed += 1
        
        if i % 10 == 0:
            await status_msg.edit_text(f"⏳ Прогресс: {i}/{len(users)} (✅ {success} | ❌ {failed})")
        
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"✅ Успешно: {success}\n"
        f"❌ Ошибок: {failed}\n"
        f"📊 Всего: {len(users)}"
    )

# ---------- СТАТИСТИКА ----------
@dp.message(Command("users"))
async def cmd_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    users = get_all_users()
    await message.answer(f"👥 Всего пользователей: {len(users)}")

# ---------- ПОМОЩЬ ----------
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    help_text = """
**👑 Админ-команды:**

📁 **Файлы:**
/addfile - добавить новый файл (вечная ссылка)
/list - список всех файлов

👥 **Пользователи:**
/users - статистика пользователей
/send - рассылка (ответь на сообщение)

ℹ️ **Другое:**
/help - это меню
"""
    await message.answer(help_text)

# ---------- ЗАПУСК ----------
async def main():
    logger.info("🚀 Запуск бота...")
    
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("✅ Бот готов к работе!")
    logger.info(f"📢 Канал подписки ID: {CHANNEL_ID}")
    logger.info(f"💾 Канал-хранилище ID: {STORAGE_CHANNEL_ID}")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
