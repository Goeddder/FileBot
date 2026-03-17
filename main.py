import os
import sqlite3
import secrets
import subprocess
import sys
import time
import asyncio
import shutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait

# --- УСТАНОВКА ---
try:
    import pyrogram
except ImportError:
    subprocess.call([sys.executable, "-m", "pip", "install", "pyrogram", "tgcrypto"])

# --- НАСТРОЙКИ ---
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
ADMIN_ID = 1471307057  
CHANNEL_URL = "https://t.me/OfficialPlutonium"
CHANNEL_ID = "@OfficialPlutonium" 
STORAGE_CHANNEL = "@IllyaTelegram" 

DB_PATH = "files.db"
TEMP_DB = "restored.db" # Временный файл для восстановления
waiting_for_backup = {}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, remote_msg_id INTEGER, type TEXT, name TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

app = Client("plutonium_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- ОБРАБОТЧИКИ ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    sub_button = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на Plutonium", url=CHANNEL_URL)]])

    if len(message.command) == 1:
        return await message.reply(f"👋 Привет! Я архив проекта Plutonium. Подпишись, чтобы скачивать файлы.", reply_markup=sub_button)

    file_hash = message.command[1]
    try:
        member = await client.get_chat_member(CHANNEL_ID, user_id)
    except:
        return await message.reply("⚠️ **Доступ закрыт!**\nСначала подпишись на канал.", reply_markup=sub_button)

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT remote_msg_id FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()

    if row:
        try:
            await client.copy_message(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=row[0], reply_markup=sub_button)
        except:
            await message.reply("❌ Файл не найден в хранилище.")

# --- ИСПРАВЛЕННОЕ ВОССТАНОВЛЕНИЕ ---

@app.on_message(filters.command("restore") & filters.user(ADMIN_ID))
async def restore_request(client, message):
    waiting_for_backup[message.from_user.id] = True
    await message.reply("📤 **Режим восстановления!**\nПришли файл `files.db`. Я принудительно заменю текущую базу.")

@app.on_message(filters.document & filters.user(ADMIN_ID))
async def handle_docs(client, message):
    user_id = message.from_user.id
    
    if user_id in waiting_for_backup and "files.db" in message.document.file_name:
        status = await message.reply("⏳ **Идет жесткая замена базы...**")
        try:
            # 1. Скачиваем во временный файл
            await message.download(file_name=TEMP_DB)
            
            # 2. Проверяем, что временный файл рабочий
            test_conn = sqlite3.connect(TEMP_DB)
            f_count = test_conn.execute("SELECT count(*) FROM files").fetchone()[0]
            test_conn.close()
            
            # 3. Копируем временный файл в основной (перезапись)
            shutil.copyfile(TEMP_DB, DB_PATH)
            os.remove(TEMP_DB) # Удаляем временный
            
            del waiting_for_backup[user_id]
            await status.edit_text(f"✅ **База заменена!**\nНайдено файлов: `{f_count}`\n\nТеперь ссылки работают.")
        except Exception as e:
            await status.edit_text(f"❌ Ошибка восстановления: {e}")
        return

    # Загрузка нового файла
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    f_hash = secrets.token_urlsafe(8)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (f_hash, sent_msg.id, "file", message.caption or "Файл"))
    conn.commit()
    conn.close()
    await message.reply(f"💎 Сохранено!\nСсылка: `https://t.me/plutoniumfilesBot?start={f_hash}`")
    await message.reply_document(DB_PATH, caption="📦 Свежий бэкап")

@app.on_message((filters.video | filters.photo) & filters.user(ADMIN_ID))
async def handle_media(client, message):
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    f_hash = secrets.token_urlsafe(8)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (f_hash, sent_msg.id, "media", message.caption or "Медиа"))
    conn.commit()
    conn.close()
    await message.reply(f"💎 Сохранено!\nСсылка: `https://t.me/plutoniumfilesBot?start={f_hash}`")
    await message.reply_document(DB_PATH, caption="📦 Свежий бэкап")

@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_files(client, message):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT hash, name FROM files").fetchall()
    conn.close()
    if not rows: return await message.reply("📭 База пуста.")
    res = "📂 **Список:**\n\n" + "\n".join([f"• {n}\n`https://t.me/plutoniumfilesBot?start={h}`" for h, n in rows])
    await message.reply(res)

@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    if not message.reply_to_message: return await message.reply("Ответь `/send` на пост.")
    conn = sqlite3.connect(DB_PATH)
    users = [u[0] for u in conn.execute("SELECT user_id FROM users").fetchall()]
    conn.close()
    status = await message.reply(f"🚀 Рассылка на {len(users)} чел...")
    count = 0
    for uid in users:
        try:
            await message.reply_to_message.copy(uid)
            count += 1
            await asyncio.sleep(0.05)
        except FloodWait as e: await asyncio.sleep(e.value)
        except: pass
    await status.edit_text(f"✅ Готово! Получили {count} чел.")

init_db()
app.run()
    
