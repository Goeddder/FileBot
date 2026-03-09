
from pyrogram import Client, filters
import sqlite3
import os
import secrets

# --- НАСТРОЙКИ (Вставлены твои данные) ---
API_ID = 39522849
API_HASH = "26909eddad0be2400fb765fad0e267f8"
BOT_TOKEN = "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw"
DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Инициализация БД
def init_db():
    conn = sqlite3.connect("files.db")
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, type TEXT, path TEXT)")
    conn.commit()
    conn.close()

# --- ОБРАБОТКА ССЫЛОК ---
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    if len(message.command) > 1:
        file_hash = message.command[1]
        conn = sqlite3.connect("files.db")
        cursor = conn.cursor()
        cursor.execute("SELECT type, path FROM files WHERE hash = ?", (file_hash,))
        row = cursor.fetchone()
        conn.close()

        if row:
            f_type, f_path = row
            try:
                # Прямая отправка файла с диска
                if f_type == 'photo': await message.reply_photo(f_path)
                elif f_type == 'video': await message.reply_video(f_path)
                else: await message.reply_document(f_path)
            except Exception as e:
                await message.reply(f"Ошибка при отправке: {e}")
        else:
            await message.reply("❌ Файл не найден.")
    else:
        await message.reply("✋ Привет! Отправь файл, чтобы получить на него ссылку.")

# --- ЗАГРУЗКА ФАЙЛОВ ---
@app.on_message(filters.document | filters.video | filters.photo)
async def admin_upload(client, message):
    # Скачиваем файл в папку
    file_path = await message.download(file_name=f"{DOWNLOAD_DIR}/")
    f_hash = secrets.token_urlsafe(16)
    f_type = 'photo' if message.photo else ('video' if message.video else 'doc')
    
    conn = sqlite3.connect("files.db")
    conn.execute("INSERT INTO files (hash, type, path) VALUES (?, ?, ?)", (f_hash, f_type, file_path))
    conn.commit()
    conn.close()
    
    await message.reply(f"✅ Готово! Ссылка: https://t.me/plutoniumfilesBot?start={f_hash}")

init_db()
print("Бот запущен...")
app.run()
