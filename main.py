import os
import sqlite3
import secrets
import asyncio
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

app = Client("plutonium_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, remote_msg_id INTEGER, type TEXT, name TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

# --- ФУНКЦИЯ АВТО-ЗАГРУЗКИ БАЗЫ ИЗ КАНАЛА ---
async def load_db_from_channel():
    print("⏳ Поиск базы в канале @IllyaTelegram...")
    try:
        async for message in app.get_chat_history(STORAGE_CHANNEL, limit=20):
            if message.document and message.document.file_name == "files.db":
                if os.path.exists(DB_PATH): os.remove(DB_PATH)
                await message.download(file_name=DB_PATH)
                print("✅ База успешно скачана из канала!")
                return True
    except Exception as e:
        print(f"❌ Ошибка загрузки базы: {e}")
    return False

# --- ФУНКЦИЯ СОХРАНЕНИЯ БАЗЫ В КАНАЛ ---
async def save_db_to_channel():
    try:
        await app.send_document(STORAGE_CHANNEL, DB_PATH, caption="📦 System Backup")
    except Exception as e:
        print(f"❌ Не удалось сохранить бэкап в канал: {e}")

# --- ОБРАБОТЧИКИ ---

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    if len(message.command) > 1:
        file_hash = message.command[1]
        try:
            await client.get_chat_member(CHANNEL_ID, user_id)
        except:
            return await message.reply("❌ Подпишись на канал для доступа!", 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL)]]))

        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT remote_msg_id FROM files WHERE hash = ?", (file_hash,)).fetchone()
        conn.close()
        if row:
            await client.copy_message(message.chat.id, STORAGE_CHANNEL, row[0])
    else:
        await message.reply("👋 Бот Plutonium работает!")

@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def admin_upload(client, message):
    st = await message.reply("⏳ Сохранение...")
    sent = await message.copy(STORAGE_CHANNEL)
    h = secrets.token_urlsafe(8)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (h, sent.id, "file", message.caption or "Файл"))
    conn.commit()
    conn.close()
    
    await st.edit_text(f"💎 Ссылка: `https://t.me/plutoniumfilesBot?start={h}`")
    # Авто-бэкап в канал
    await save_db_to_channel()

@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_cmd(client, message):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT hash, name FROM files").fetchall()
    conn.close()
    if not rows: return await message.reply("📭 База пуста.")
    res = "📂 Файлы:\n" + "\n".join([f"`https://t.me/plutoniumfilesBot?start={h}`" for h, n in rows])
    await message.reply(res)

@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def send_cmd(client, message):
    if not message.reply_to_message: return await message.reply("Ответь `/send` на пост!")
    conn = sqlite3.connect(DB_PATH)
    users = [u[0] for u in conn.execute("SELECT user_id FROM users").fetchall()]
    conn.close()
    for uid in users:
        try:
            await message.reply_to_message.copy(uid)
            await asyncio.sleep(0.1)
        except: pass
    await message.reply("✅ Рассылка завершена!")

# --- ЗАПУСК ---
async def main():
    init_db()
    await app.start()
    await load_db_from_channel() # Пробуем восстановиться сами
    print("--- БОТ ЗАПУЩЕН ---")
    await asyncio.Event().wait()

if __name__ == "__main__":
    app.run(main())
