import asyncio
import sqlite3
import secrets
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ========== НАСТРОЙКИ ==========
TOKEN = "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw"
ADMIN_ID = 1471307057
CHANNEL_URL = "https://t.me/OfficialPlutonium"
# ================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- ПРОСТАЯ БАЗА ----------
def init_db():
    conn = sqlite3.connect('files.db')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            hash TEXT PRIMARY KEY,
            file_id TEXT,
            file_name TEXT,
            caption TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()
    logger.info("✅ База готова")

def save_user(user_id):
    conn = sqlite3.connect('files.db')
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def save_file(file_hash, file_id, file_name, caption):
    conn = sqlite3.connect('files.db')
    conn.execute("INSERT INTO files (hash, file_id, file_name, caption) VALUES (?, ?, ?, ?)",
                (file_hash, file_id, file_name, caption))
    conn.commit()
    conn.close()

def get_file(file_hash):
    conn = sqlite3.connect('files.db')
    row = conn.execute("SELECT file_id, file_name, caption FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()
    return row

def get_all_files():
    conn = sqlite3.connect('files.db')
    rows = conn.execute("SELECT hash, file_name FROM files ORDER BY rowid DESC").fetchall()
    conn.close()
    return rows

def get_all_users():
    conn = sqlite3.connect('files.db')
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return rows

# ---------- КОМАНДА СТАРТ ----------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    
    channel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Канал Plutonium", url=CHANNEL_URL)]
    ])

    if len(message.text.split()) == 1:
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"Я бот Plutonium. Перейди по ссылке, чтобы получить файл.",
            reply_markup=channel_btn
        )
        return

    file_hash = message.text.split()[1]
    file_info = get_file(file_hash)
    
    if not file_info:
        await message.answer("❌ Файл не найден")
        return
    
    file_id, file_name, caption = file_info
    
    if caption:
        await message.answer_document(
            document=file_id,
            caption=f"📁 **{file_name}**\n\n{caption}",
            reply_markup=channel_btn
        )
    else:
        await message.answer_document(
            document=file_id,
            caption=f"📁 **{file_name}**",
            reply_markup=channel_btn
        )

# ---------- ДОБАВЛЕНИЕ ФАЙЛА ----------
@dp.message(Command("addfile"))
async def addfile_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📤 Отправь мне файл (можно с описанием)")

@dp.message(F.document | F.video | F.photo)
async def get_file_from_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "документ"
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "видео"
    else:
        file_id = message.photo[-1].file_id
        file_name = "фото"
    
    file_hash = secrets.token_urlsafe(8)
    caption = message.caption or ""
    save_file(file_hash, file_id, file_name, caption)
    
    # Отправляем бэкап базы админу
    with open('files.db', 'rb') as f:
        await bot.send_document(
            chat_id=ADMIN_ID,
            document=FSInputFile('files.db'),
            caption=f"📦 Бэкап после добавления {file_name}"
        )
    
    bot_me = await bot.get_me()
    url = f"https://t.me/{bot_me.username}?start={file_hash}"
    
    await message.answer(
        f"✅ **Файл сохранён!**\n\n"
        f"📁 **{file_name}**\n"
        f"🔗 `{url}`"
    )

# ---------- ВОССТАНОВЛЕНИЕ БАЗЫ ----------
@dp.message(Command("restore"))
async def restore_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer("📤 Отправь мне файл `files.db` для восстановления базы")

@dp.message(F.document)
async def handle_restore(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if message.document.file_name != "files.db":
        await message.answer("❌ Это не файл базы данных. Нужен files.db")
        return
    
    # Скачиваем файл
    file = await bot.download_file(message.document.file_id)
    
    # Сохраняем поверх старой базы
    with open('files.db', 'wb') as f:
        f.write(file.getbuffer())
    
    await message.answer("✅ База данных восстановлена!\nВсе ссылки снова работают.")

# ---------- СПИСОК ФАЙЛОВ ----------
@dp.message(Command("list"))
async def list_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    files = get_all_files()
    if not files:
        await message.answer("📭 Нет файлов")
        return
    
    bot_me = await bot.get_me()
    text = "📂 **Все файлы:**\n\n"
    
    for h, name in files:
        url = f"https://t.me/{bot_me.username}?start={h}"
        text += f"📁 {name}\n`{url}`\n\n"
        
        if len(text) > 3500:
            await message.answer(text)
            text = ""
    
    if text:
        await message.answer(text)

# ---------- РАССЫЛКА ----------
@dp.message(Command("send"))
async def send_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not message.reply_to_message:
        await message.answer("❌ Ответь на сообщение для рассылки")
        return
    
    users = get_all_users()
    if not users:
        await message.answer("📭 Нет пользователей")
        return
    
    status = await message.answer(f"📢 Рассылка {len(users)} пользователям...")
    
    success = 0
    for uid in users:
        try:
            await message.reply_to_message.copy(uid[0])
            success += 1
            if success % 10 == 0:
                await status.edit_text(f"⏳ Прогресс: {success}/{len(users)}")
            await asyncio.sleep(0.05)
        except:
            pass
    
    await status.edit_text(f"✅ Разослано: {success}/{len(users)}")

# ---------- СТАТИСТИКА ----------
@dp.message(Command("users"))
async def users_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = get_all_users()
    await message.answer(f"👥 Всего пользователей: {len(users)}")

# ---------- ЗАПУСК ----------
async def main():
    logger.info("🚀 Запуск бота...")
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Бот готов!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
