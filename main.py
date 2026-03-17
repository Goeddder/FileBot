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

# --- АВТО-УСТАНОВКА БИБЛИОТЕК ---
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
waiting_for_backup = {}

# --- ИНИЦИАЛИЗАЦИЯ БД ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, remote_msg_id INTEGER, type TEXT, name TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def check_subscription(client, user_id):
    try:
        await client.get_chat_member(CHANNEL_ID, user_id)
        return True
    except UserNotParticipant: return False
    except: return True

async def progress(current, total, message, start_time):
    percent = (current * 100) / total
    elapsed = time.time() - start_time
    if int(percent) % 20 == 0:
        try:
            await message.edit_text(f"🚀 Отправка: {percent:.1f}%\n⏱ Время: {elapsed:.1f} сек.")
        except: pass

app = Client("plutonium_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- ОБРАБОТЧИКИ ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # Сохраняем пользователя для рассылки
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    sub_button = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на Plutonium", url=CHANNEL_URL)]])

    # Приветствие
    if len(message.command) == 1:
        welcome_text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "🤖 Я бот-архив проекта **Plutonium**.\n"
            "Чтобы скачивать файлы, ты должен быть подписан на наш канал."
        )
        return await message.reply(welcome_text, reply_markup=sub_button)

    # Получение файла
    file_hash = message.command[1]
    if not await check_subscription(client, user_id):
        return await message.reply("⚠️ **Доступ закрыт!**\nСначала подпишись на канал проекта.", reply_markup=sub_button)

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT remote_msg_id, type FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()

    if row:
        msg_id, f_type = row
        start_time = time.time()
        status_msg = await message.reply("⏳ Извлечение из архива...")
        try:
            await client.copy_message(
                chat_id=message.chat.id, 
                from_chat_id=STORAGE_CHANNEL, 
                message_id=msg_id, 
                reply_markup=sub_button
            )
            total_time = time.time() - start_time
            await status_msg.edit_text(f"✅ Файл доставлен за {total_time:.1f} сек.")
        except:
            await status_msg.edit_text("❌ Ошибка: Файл удален из хранилища.")

# КОМАНДА ВОССТАНОВЛЕНИЯ
@app.on_message(filters.command("restore") & filters.user(ADMIN_ID))
async def restore_request(client, message):
    waiting_for_backup[message.from_user.id] = True
    await message.reply("📤 **Режим восстановления!**\nПришли файл `files.db`, чтобы вернуть ссылки и юзеров.")

# ОБРАБОТКА ДОКУМЕНТОВ (Бэкап или Загрузка)
@app.on_message(filters.document & filters.user(ADMIN_ID))
async def handle_docs(client, message):
    user_id = message.from_user.id
    
    # Если ждем бэкап
    if user_id in waiting_for_backup and message.document.file_name == "files.db":
        status = await message.reply("⏳ Восстановление...")
        await message.download(file_name=DB_PATH)
        if user_id in waiting_for_backup: del waiting_for_backup[user_id]
        return await status.edit_text("✅ База данных успешно заменена!")

    # Если просто загрузка файла в архив
    status = await message.reply("⏳ Сохранение...")
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    f_hash = secrets.token_urlsafe(8)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (f_hash, sent_msg.id, "doc", message.caption or "Документ"))
    conn.commit()
    conn.close()
    
    url = f"https://t.me/plutoniumfilesBot?start={f_hash}"
    await status.edit_text(f"💎 **Файл сохранен!**\n\nСсылка (копируется нажатием):\n`{url}`")
    await message.reply_document(DB_PATH, caption="📦 Твой новый бэкап базы")

# ЗАГРУЗКА ВИДЕО/ФОТО
@app.on_message((filters.video | filters.photo) & filters.user(ADMIN_ID))
async def handle_media(client, message):
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    f_hash = secrets.token_urlsafe(8)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (f_hash, sent_msg.id, "media", message.caption or "Медиа"))
    conn.commit()
    conn.close()
    await message.reply(f"💎 **Медиа сохранено!**\n\nСсылка:\n`https://t.me/plutoniumfilesBot?start={f_hash}`")
    await message.reply_document(DB_PATH, caption="📦 Твой новый бэкап базы")

# РАССЫЛКА
@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    if not message.reply_to_message:
        return await message.reply("Ответь на сообщение командой `/send`.")
    
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()

    status = await message.reply(f"🚀 Рассылка на {len(users)} чел...")
    count = 0
    for (uid,) in users:
        try:
            await message.reply_to_message.copy(uid)
            count += 1
            if count % 10 == 0: await status.edit_text(f"Прогресс: {count}/{len(users)}")
            await asyncio.sleep(0.05)
        except FloodWait as e: await asyncio.sleep(e.value)
        except: pass
    await status.edit_text(f"✅ Рассылка завершена. Получили {count} чел.")

# СПИСОК ФАЙЛОВ
@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_files(client, message):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT hash, name FROM files").fetchall()
    conn.close()
    if not rows: return await message.reply("База пуста.")
    res = "📂 **Твои файлы:**\n\n" + "\n".join([f"• {n}\n`https://t.me/plutoniumfilesBot?start={h}`" for h, n in rows])
    await message.reply(res)

init_db()
print("--- БОТ PLUTONIUM ЗАПУЩЕН ---")
app.run()
                
