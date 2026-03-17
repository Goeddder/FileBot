import os
import sqlite3
import secrets
import subprocess
import sys
import asyncio
import shutil
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait

# --- НАСТРОЙКИ ---
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
ADMIN_ID = 1471307057  
CHANNEL_URL = "https://t.me/OfficialPlutonium"
CHANNEL_ID = "@OfficialPlutonium" 
STORAGE_CHANNEL = "@IllyaTelegram" 

DB_PATH = "files.db"
waiting_for_backup = {}

# --- ИНИЦИАЛИЗАЦИЯ ---
def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, remote_msg_id INTEGER, type TEXT, name TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

app = Client("plutonium_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- ФУНКЦИИ ---
async def check_sub(client, user_id):
    try:
        await client.get_chat_member(CHANNEL_ID, user_id)
        return True
    except UserNotParticipant: return False
    except: return True

# --- ОБРАБОТЧИКИ ---

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    init_db()
    
    # Сохраняем юзера для рассылки
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    sub_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на Plutonium", url=CHANNEL_URL)]])

    if len(message.command) == 1:
        return await message.reply(f"👋 Привет, {message.from_user.first_name}!\nЯ архив проекта Plutonium. Подпишись для доступа.", reply_markup=sub_kb)

    # Выдача файла
    if not await check_sub(client, user_id):
        return await message.reply("⚠️ **Доступ закрыт!** Подпишись на канал.", reply_markup=sub_kb)

    file_hash = message.command[1]
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT remote_msg_id FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()

    if row:
        try:
            await client.copy_message(message.chat.id, STORAGE_CHANNEL, row[0], reply_markup=sub_kb)
        except:
            await message.reply("❌ Файл не найден в хранилище.")

# ВОССТАНОВЛЕНИЕ (RESTORE)
@app.on_message(filters.command("restore") & filters.user(ADMIN_ID))
async def restore_req(client, message):
    waiting_for_backup[message.from_user.id] = True
    await message.reply("📤 **Режим восстановления!**\nПришли файл `files.db`. Текущая база будет стерта и заменена!")

@app.on_message(filters.document & filters.user(ADMIN_ID))
async def handle_docs(client, message):
    user_id = message.from_user.id
    
    if user_id in waiting_for_backup and "files.db" in message.document.file_name:
        status = await message.reply("⏳ **Жесткая замена базы...**")
        try:
            temp_path = "temp_restore.db"
            await message.download(file_name=temp_path)
            
            # Проверка структуры в присланном файле
            check_conn = sqlite3.connect(temp_path)
            # Если таблиц нет - создаем их, чтобы не было ошибки 'no such table'
            check_conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, remote_msg_id INTEGER, type TEXT, name TEXT)")
            check_conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
            f_count = check_conn.execute("SELECT count(*) FROM files").fetchone()[0]
            u_count = check_conn.execute("SELECT count(*) FROM users").fetchone()[0]
            check_conn.close()

            # Удаляем старую, ставим новую
            if os.path.exists(DB_PATH): os.remove(DB_PATH)
            shutil.move(temp_path, DB_PATH)
            
            del waiting_for_backup[user_id]
            await status.edit_text(f"✅ **Успех!**\nФайлов: `{f_count}`\nЮзеров: `{u_count}`\n\nТеперь `/list` должен работать.")
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {e}")
        return

    # Обычная загрузка нового файла
    st = await message.reply("⏳ Сохраняю...")
    sent = await message.copy(STORAGE_CHANNEL)
    h = secrets.token_urlsafe(8)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (h, sent.id, "doc", message.caption or "Файл"))
    conn.commit()
    conn.close()
    await st.edit_text(f"💎 Ссылка: `https://t.me/plutoniumfilesBot?start={h}`")
    await message.reply_document(DB_PATH, caption="📦 Твой бэкап")

# МЕДИА ЗАГРУЗКА
@app.on_message((filters.video | filters.photo) & filters.user(ADMIN_ID))
async def handle_media(client, message):
    sent = await message.copy(STORAGE_CHANNEL)
    h = secrets.token_urlsafe(8)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (h, sent.id, "media", message.caption or "Медиа"))
    conn.commit()
    conn.close()
    await message.reply(f"💎 Ссылка: `https://t.me/plutoniumfilesBot?start={h}`\n📦 Бэкап ниже:")
    await message.reply_document(DB_PATH)

# СПИСОК
@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_cmd(client, message):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT hash, name FROM files").fetchall()
    conn.close()
    if not rows: return await message.reply("📭 База пуста.")
    res = "📂 **Файлы в базе:**\n\n" + "\n".join([f"• {n}\n`https://t.me/plutoniumfilesBot?start={h}`" for h, n in rows])
    await message.reply(res)

# РАССЫЛКА
@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def send_cmd(client, message):
    if not message.reply_to_message: return await message.reply("Ответь `/send` на пост!")
    conn = sqlite3.connect(DB_PATH)
    users = [u[0] for u in conn.execute("SELECT user_id FROM users").fetchall()]
    conn.close()
    
    st = await message.reply(f"🚀 Рассылка на {len(users)} чел...")
    c = 0
    for uid in users:
        try:
            await message.reply_to_message.copy(uid)
            c += 1
            if c % 10 == 0: await st.edit_text(f"Прогресс: {c}/{len(users)}")
            await asyncio.sleep(0.05)
        except FloodWait as e: await asyncio.sleep(e.value)
        except: pass
    await st.edit_text(f"✅ Готово! Получили: {c}")

init_db()
app.run()
    
