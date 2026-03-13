import os
import sqlite3
import secrets
import subprocess
import sys
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait

# 1. АВТО-УСТАНОВКА БИБЛИОТЕК
try:
    import pyrogram
except ImportError:
    subprocess.call([sys.executable, "-m", "pip", "install", "pyrogram", "tgcrypto"])

# 2. НАСТРОЙКИ
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
ADMIN_ID = 1471307057  
CHANNEL_URL = "https://t.me/OfficialPlutonium" # Канал для подписки
CHANNEL_ID = "@OfficialPlutonium" 
STORAGE_CHANNEL = "@IllyaTelegram" # Канал-хранилище (бот должен быть админом!)

DB_PATH = "files.db"

app = Client("plutonium_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Инициализация БД (добавлена таблица users для рассылки)
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, remote_msg_id INTEGER, type TEXT, name TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

async def check_subscription(client, user_id):
    try:
        await client.get_chat_member(CHANNEL_ID, user_id)
        return True
    except UserNotParticipant: return False
    except: return True

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # Регистрация пользователя для рассылки
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    sub_button = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на Plutonium", url=CHANNEL_URL)]])

    if len(message.command) == 1:
        return await message.reply(
            f"👋 Привет, {message.from_user.first_name}!\n\nЯ бот-архив проекта Plutonium. Подпишись на канал, чтобы получать файлы.",
            reply_markup=sub_button
        )

    # Получение файла
    file_hash = message.command[1]
    if not await check_subscription(client, user_id):
        return await message.reply("⚠️ **Доступ закрыт!**\nСначала подпишись на канал.", reply_markup=sub_button)

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT remote_msg_id, type FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()

    if row:
        msg_id, f_type = row
        try:
            # Пересылаем файл из канала-хранилища
            await client.copy_message(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id, reply_markup=sub_button)
        except Exception as e:
            await message.reply(f"❌ Ошибка доступа к хранилищу. Убедитесь, что файл в {STORAGE_CHANNEL} не удален.")

@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def admin_upload(client, message):
    # Пересылаем файл в хранилище
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    
    f_hash = secrets.token_urlsafe(8)
    f_type = 'photo' if message.photo else ('video' if message.video else 'doc')
    name = message.caption or "Файл"

    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (f_hash, sent_msg.id, f_type, name))
    conn.commit()
    conn.close()

    url = f"https://t.me/plutoniumfilesBot?start={f_hash}"
    await message.reply(f"💎 **Файл в архиве!**\n\nНазвание: `{name}`\nСсылка:\n`{url}`")
    try: await message.reply_document(DB_PATH, caption="📦 Бэкап базы")
    except: pass

@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_files(client, message):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT hash, name FROM files").fetchall()
    conn.close()
    if not rows: return await message.reply("Пусто.")
    res = "📂 **Список:**\n\n" + "\n".join([f"• {n}\n`https://t.me/plutoniumfilesBot?start={h}`" for h, n in rows])
    await message.reply(res)

# РАССЫЛКА
@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    if not message.reply_to_message:
        return await message.reply("Ответь командой `/send` на сообщение, которое хочешь разослать.")
    
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()

    count = 0
    status = await message.reply(f"🚀 Начинаю рассылку на {len(users)} чел...")
    
    for (uid,) in users:
        try:
            await message.reply_to_message.copy(uid)
            count += 1
            if count % 20 == 0: await status.edit_text(f"Прогресс: {count}/{len(users)}")
            await asyncio.sleep(0.05) # Защита от спам-фильтра
        except FloodWait as e: await asyncio.sleep(e.value)
        except: pass
    
    await status.edit_text(f"✅ Рассылка завершена! Получили {count} пользователей.")

init_db()
app.run()
    
