import os
import subprocess
import sys
import sqlite3
import secrets
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- 1. БЛОК САМОУСТАНОВКИ (Защита от ошибки отсутствия библиотек) ---
def install_requirements():
    try:
        import pyrogram
    except ImportError:
        print("Библиотеки не найдены, устанавливаю...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyrogram", "tgcrypto"])
        print("Установка завершена!")

install_requirements()

# --- 2. НАСТРОЙКИ ---
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
CHANNEL_URL = "https://t.me/ТВОЯ_ССЫЛКА_НА_КАНАЛ" # ЗАМЕНИ НА СВОЮ

# Папка для файлов (в Railway используй /app/downloads)
BASE_DIR = "/app/downloads"
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)
DB_PATH = os.path.join(BASE_DIR, "files.db")

app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- 3. РАБОТА С БД ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, type TEXT, path TEXT)")
    conn.commit()
    conn.close()

# --- 4. ОБРАБОТЧИКИ ---
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    if len(message.command) > 1:
        file_hash = message.command[1]
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT type, path FROM files WHERE hash = ?", (file_hash,)).fetchone()
        conn.close()
        
        if row:
            f_type, f_path = row
            # Кнопка, которую пользователь не может убрать с сообщения
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_URL)]
            ])
            
            try:
                if f_type == 'photo': await message.reply_photo(f_path, reply_markup=buttons)
                elif f_type == 'video': await message.reply_video(f_path, reply_markup=buttons)
                else: await message.reply_document(f_path, reply_markup=buttons)
            except Exception as e:
                print(f"Ошибка отправки: {e}")
        # Если файла нет в базе, бот просто ничего не делает (молчит)

@app.on_message(filters.document | filters.video | filters.photo)
async def admin_upload(client, message):
    # Скачиваем файл в папку
    file_path = await message.download(file_name=f"{BASE_DIR}/")
    f_hash = secrets.token_urlsafe(16)
    f_type = 'photo' if message.photo else ('video' if message.video else 'doc')
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files (hash, type, path) VALUES (?, ?, ?)", (f_hash, f_type, file_path))
    conn.commit()
    conn.close()
    
    await message.reply(f"✅ Файл загружен!\nСсылка: https://t.me/plutoniumfilesBot?start={f_hash}")

# --- 5. ЗАПУСК ---
init_db()
print("Бот запущен...")
app.run()
    
