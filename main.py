import os
import sqlite3
import secrets
import subprocess
import sys
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

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
CHANNEL_ID = "@OfficialPlutonium" # ID канала для проверки подписки

DB_PATH = "files.db"

app = Client("plutonium_cloud", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Прогресс отправки
async def progress(current, total, message, start_time):
    percent = (current * 100) / total
    elapsed = time.time() - start_time
    if int(percent) % 20 == 0:
        try:
            await message.edit_text(f"🚀 Отправка: {percent:.1f}%\n⏱ Время: {elapsed:.1f} сек.")
        except: pass

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, file_id TEXT, type TEXT, name TEXT)")
    conn.commit()
    conn.close()

# Проверка подписки
async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(CHANNEL_ID, user_id)
        return True
    except UserNotParticipant:
        return False
    except Exception:
        return True # Если ошибка API, пускаем пользователя

# --- ОБРАБОТЧИКИ ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # Кнопка подписки
    sub_button = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на Plutonium", url=CHANNEL_URL)]])

    # Если это просто старт без параметров (приветствие)
    if len(message.command) == 1:
        welcome_text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "🤖 Я — бот-хранилище файлов проекта **Plutonium**.\n"
            "Здесь ты можешь получать доступ к эксклюзивным файлам.\n\n"
            "👇 Чтобы пользоваться ботом, обязательно подпишись на наш канал!"
        )
        return await message.reply(welcome_text, reply_markup=sub_button)

    # Если есть параметр (попытка получить файл)
    file_hash = message.command[1]
    
    # ПРОВЕРКА ПОДПИСКИ
    is_subscribed = await check_subscription(client, user_id)
    if not is_subscribed:
        return await message.reply(
            "⚠️ **Доступ ограничен!**\n\nДля получения файла вы должны быть подписаны на наш канал.",
            reply_markup=sub_button
        )

    # Поиск файла в базе
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT file_id, type FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()
    
    if row:
        f_id, f_type = row
        start_time = time.time()
        
        if f_type == 'photo':
            await message.reply_photo(f_id, reply_markup=sub_button)
        else:
            status_msg = await message.reply("⏳ Начинаю загрузку из облака...")
            try:
                if f_type == 'video':
                    await message.reply_video(f_id, reply_markup=sub_button, progress=progress, progress_args=(status_msg, start_time))
                else:
                    await message.reply_document(f_id, reply_markup=sub_button, progress=progress, progress_args=(status_msg, start_time))
                
                total_time = time.time() - start_time
                await status_msg.edit_text(f"✅ Файл доставлен за {total_time:.1f} сек.")
            except Exception as e:
                await status_msg.edit_text(f"❌ Ошибка: {e}")

@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def admin_upload(client, message):
    if message.photo:
        f_id = message.photo.file_id
        f_type = 'photo'
    elif message.video:
        f_id = message.video.file_id
        f_type = 'video'
    else:
        f_id = message.document.file_id
        f_type = 'doc'
    
    f_hash = secrets.token_urlsafe(8)
    name = message.caption or "Без названия"
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (f_hash, f_id, f_type, name))
    conn.commit()
    conn.close()
    
    share_url = f"https://t.me/plutoniumfilesBot?start={f_hash}"
    await message.reply(
        f"💎 **Файл сохранен!**\n\n"
        f"Название: `{name}`\n"
        f"Ссылка (копируется нажатием):\n`{share_url}`",
        protect_content=True
    )
    
    # Бэкап БД админу
    try: await message.reply_document(DB_PATH, caption="📦 Бэкап базы")
    except: pass

@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_files(client, message):
    conn = sqlite3.connect(DB_PATH)
    files = conn.execute("SELECT hash, name FROM files").fetchall()
    conn.close()
    
    if not files: return await message.reply("📭 Пусто.")
    
    text = "📂 **Список файлов:**\n\n"
    for h, name in files:
        url = f"https://t.me/plutoniumfilesBot?start={h}"
        text += f"🔹 {name}\n`{url}`\n\n"
    await message.reply(text)

init_db()
print("--- БОТ ЗАПУЩЕН С ПОДПИСКОЙ ---")
app.run()
