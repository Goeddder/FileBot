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
CHANNEL_URL = "https://t.me/OfficialPlutonium"
CHANNEL_ID = "@OfficialPlutonium" 
STORAGE_CHANNEL = "@IllyaTelegram" 

DB_PATH = "files.db"

app = Client("plutonium_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Состояние для восстановления базы
waiting_for_backup = {}

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
    if not await check_subscription(client, user_id):
        return await message.reply("⚠️ **Доступ закрыт!**\nСначала подпишись на канал.", reply_markup=sub_button)

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT remote_msg_id, type FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()

    if row:
        msg_id, f_type = row
        try:
            await client.copy_message(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id, reply_markup=sub_button)
        except:
            await message.reply("❌ Ошибка доступа к хранилищу.")

# КОМАНДА ВОССТАНОВЛЕНИЯ
@app.on_message(filters.command("restore") & filters.user(ADMIN_ID))
async def restore_request(client, message):
    waiting_for_backup[message.from_user.id] = True
    await message.reply("📤 Отправь мне файл `files.db`, чтобы восстановить базу данных.")

# ОБРАБОТКА ФАЙЛА БЭКАПА
@app.on_message(filters.document & filters.user(ADMIN_ID))
async def handle_restore(client, message):
    if message.from_user.id in waiting_for_backup:
        if message.document.file_name == "files.db":
            status = await message.reply("⏳ Восстановление базы...")
            try:
                # Скачиваем новый файл поверх старого
                await message.download(file_name=DB_PATH)
                del waiting_for_backup[message.from_user.id]
                await status.edit_text("✅ База данных успешно восстановлена! Теперь старые ссылки снова работают.")
            except Exception as e:
                await status.edit_text(f"❌ Ошибка при восстановлении: {e}")
        else:
            await message.reply("⚠️ Пожалуйста, отправь файл с названием `files.db`.")
        return

    # Если это не восстановление, а обычная загрузка админом
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    f_hash = secrets.token_urlsafe(8)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (f_hash, sent_msg.id, "file", message.caption or "Файл"))
    conn.commit()
    conn.close()
    await message.reply(f"💎 Сохранено!\nСсылка: `https://t.me/plutoniumfilesBot?start={f_hash}`")
    try: await message.reply_document(DB_PATH, caption="📦 Бэкап базы")
    except: pass

@app.on_message((filters.video | filters.photo) & filters.user(ADMIN_ID))
async def admin_media_upload(client, message):
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    f_hash = secrets.token_urlsafe(8)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (f_hash, sent_msg.id, "media", message.caption or "Медиа"))
    conn.commit()
    conn.close()
    await message.reply(f"💎 Сохранено!\nСсылка: `https://t.me/plutoniumfilesBot?start={f_hash}`")
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

@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    if not message.reply_to_message:
        return await message.reply("Ответь на сообщение командой `/send`.")
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    count = 0
    status = await message.reply(f"🚀 Рассылка {len(users)} чел...")
    for (uid,) in users:
        try:
            await message.reply_to_message.copy(uid)
            count += 1
            if count % 15 == 0: await status.edit_text(f"Прогресс: {count}/{len(users)}")
            await asyncio.sleep(0.05)
        except FloodWait as e: await asyncio.sleep(e.value)
        except: pass
    await status.edit_text(f"✅ Готово! Получили {count} чел.")

init_db()
app.run()
    
