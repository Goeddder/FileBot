import os
import sqlite3
import secrets
from pyrogram import Client, filters

# Получаем настройки из переменных окружения (в Railway это безопаснее всего)
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")

# Путь к папке и БД (важно для Railway Volumes!)
BASE_DIR = "/app/downloads"
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

DB_PATH = os.path.join(BASE_DIR, "files.db")

app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, type TEXT, path TEXT)")
    conn.commit()
    conn.close()

@app.on_message(filters.command("start"))
async def start_handler(client, message):
    if len(message.command) > 1:
        file_hash = message.command[1]
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT type, path FROM files WHERE hash = ?", (file_hash,)).fetchone()
        conn.close()
        
        if row:
            f_type, f_path = row
            # Отправляем файл напрямую с диска
            try:
                if f_type == 'photo': await message.reply_photo(f_path)
                elif f_type == 'video': await message.reply_video(f_path)
                else: await message.reply_document(f_path)
            except Exception as e:
                await message.reply(f"Ошибка при отправке: {e}")
        else:
            await message.reply("❌ Файл не найден.")

@app.on_message(filters.document | filters.video | filters.photo)
async def admin_upload(client, message):
    # Скачиваем файл в Volume
    file_path = await message.download(file_name=f"{BASE_DIR}/")
    f_hash = secrets.token_urlsafe(16)
    f_type = 'photo' if message.photo else ('video' if message.video else 'doc')
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files (hash, type, path) VALUES (?, ?, ?)", (f_hash, f_type, file_path))
    conn.commit()
    conn.close()
    await message.reply(f"✅ Готово! Ссылка: https://t.me/plutoniumfilesBot?start={f_hash}")

init_db()
app.run()
