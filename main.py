from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import os

# --- НАСТРОЙКИ ---
API_ID = 1234567  # Получи на my.telegram.org
API_HASH = "твои_данные"
BOT_TOKEN = "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw"
DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# База данных
def init_db():
    conn = sqlite3.connect("files.db")
    conn.execute("CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, type TEXT, path TEXT)")
    conn.commit()
    conn.close()

# --- ЛОГИКА ОТПРАВКИ ---
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    if len(message.command) > 1:
        file_id = message.command[1]
        conn = sqlite3.connect("files.db")
        cursor = conn.cursor()
        cursor.execute("SELECT type, path FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            f_type, f_path = row
            # Pyrogram сам умеет отправлять файлы с диска максимально быстро
            try:
                if f_type == 'photo': await message.reply_photo(f_path)
                elif f_type == 'video': await message.reply_video(f_path)
                else: await message.reply_document(f_path)
            except Exception as e:
                await message.reply(f"Ошибка: {e}")
        else:
            await message.reply("❌ Файл не найден.")

# --- АДМИН-ЗАГРУЗКА ---
@app.on_message(filters.document | filters.video | filters.photo)
async def admin_upload(client, message):
    # Логика сохранения аналогична: скачиваем файл, пишем путь в БД
    file_path = await message.download(file_name=DOWNLOAD_DIR + "/")
    
    # Запрашиваем ID файла через FSM (в Pyrogram реализовано через обработчики сообщений)
    await message.reply("📥 Файл принят! Введи ID для этого файла:")
    
    # Ожидаем следующее сообщение с ID (используем фильтр)
    @app.on_message(filters.text, group=1)
    async def get_id(c, m):
        conn = sqlite3.connect("files.db")
        conn.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?)", (m.text, "doc", file_path))
        conn.commit()
        conn.close()
        await m.reply(f"✅ Готово! Ссылка: t.me/plutoniumfilesBot?start={m.text}")
        # Удаляем обработчик после получения ID
        c.remove_handler(get_id, group=1)

init_db()
app.run()
