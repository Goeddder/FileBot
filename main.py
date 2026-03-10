import os
import sqlite3
import secrets
import subprocess
import sys
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# 1. АВТО-УСТАНОВКА БИБЛИОТЕК
try:
    import pyrogram
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyrogram", "tgcrypto"])

# 2. НАСТРОЙКИ (Твои данные уже вшиты)
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
ADMIN_ID = 1471307057  # Твой ID
CHANNEL_URL = "https://t.me/OfficialPlutonium" # Твой канал

# База данных (будет лежать в корне проекта)
DB_PATH = "files.db"

app = Client("plutonium_cloud", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Функция для прогресса отправки (визуализация %)
async def progress(current, total, message, start_time):
    percent = (current * 100) / total
    elapsed = time.time() - start_time
    # Обновляем текст каждые 15% чтобы Телеграм не забанил за частые запросы
    if int(percent) % 15 == 0:
        try:
            await message.edit_text(f"🚀 Отправка файла: {percent:.1f}%\n⏱ Прошло времени: {elapsed:.1f} сек.")
        except: pass

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, file_id TEXT, type TEXT, name TEXT)")
    conn.commit()
    conn.close()

# --- ОБРАБОТЧИКИ ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    if len(message.command) > 1:
        file_hash = message.command[1]
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT file_id, type FROM files WHERE hash = ?", (file_hash,)).fetchone()
        conn.close()
        
        if row:
            f_id, f_type = row
            # Кнопка подписки (неубираемая, так как прикреплена к сообщению)
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на Plutonium", url=CHANNEL_URL)]])
            
            start_time = time.time()
            status_msg = await message.reply("⏳ Подготовка файла к отправке...")
            
            try:
                if f_type == 'photo':
                    await message.reply_photo(f_id, reply_markup=buttons)
                elif f_type == 'video':
                    await message.reply_video(f_id, reply_markup=buttons, progress=progress, progress_args=(status_msg, start_time))
                else:
                    await message.reply_document(f_id, reply_markup=buttons, progress=progress, progress_args=(status_msg, start_time))
                
                # Показываем финальное время отправки
                total_time = time.time() - start_time
                await status_msg.edit_text(f"✅ Файл успешно доставлен за {total_time:.1f} сек.")
            except Exception as e:
                await status_msg.edit_text(f"❌ Ошибка при отправке: {e}")
        # Если хеш неверный — бот просто молчит

@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def admin_upload(client, message):
    # Определяем тип и берем file_id (он уникален для облака ТГ)
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
    
    # Ссылку видит ТОЛЬКО админ при загрузке
    await message.reply(f"💎 **Файл в облаке!**\n\nНазвание: {name}\nСсылка: `https://t.me/plutoniumfilesBot?start={f_hash}`", protect_content=True)

@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_files(client, message):
    conn = sqlite3.connect(DB_PATH)
    files = conn.execute("SELECT hash, name FROM files").fetchall()
    conn.close()
    
    if not files:
        return await message.reply("📭 В базе пока нет файлов.")
    
    text = "📂 **Список всех загруженных файлов:**\n\n"
    for h, name in files:
        text += f"🔹 {name}\n🔗 `https://t.me/plutoniumfilesBot?start={h}`\n\n"
    await message.reply(text)

@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    if len(message.command) < 2:
        return await message.reply("Пример: `/send Текст рассылки`")
    
    broadcast_text = message.text.split(maxsplit=1)[1]
    await message.reply(f"📢 Рассылка запущена (заглушка):\n\n{broadcast_text}")
    # Здесь можно добавить цикл по базе пользователей, если будешь их сохранять в БД

init_db()
print("--- БОТ ЗАПУЩЕН В ОБЛАЧНОМ РЕЖИМЕ ---")
app.run()
