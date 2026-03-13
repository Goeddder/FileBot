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

# 1. АВТО-УСТАНОВКА БИБЛИОТЕК (Железная защита от ModuleNotFoundError)
try:
    import pyrogram
except ImportError:
    subprocess.call([sys.executable, "-m", "pip", "install", "pyrogram", "tgcrypto"])

# 2. НАСТРОЙКИ (Вшиты твои данные)
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
ADMIN_ID = 1471307057  
CHANNEL_URL = "https://t.me/OfficialPlutonium" # Для кнопки
CHANNEL_ID = "@OfficialPlutonium" # Для проверки подписки
STORAGE_CHANNEL = "@IllyaTelegram" # Твое хранилище (Бот должен быть админом там!)

DB_PATH = "files.db"

app = Client("plutonium_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

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
    except: return True # Если ошибка, пускаем юзера, чтобы не ломать бота

# --- ОБРАБОТЧИКИ ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # Регистрация юзера для будущей рассылки
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    sub_button = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на Plutonium", url=CHANNEL_URL)]])

    # Если просто запуск бота
    if len(message.command) == 1:
        return await message.reply(
            f"👋 Привет, {message.from_user.first_name}!\n\nЯ бот-архив проекта **Plutonium**. Подпишись на канал, чтобы скачивать файлы.",
            reply_markup=sub_button
        )

    # Если человек пришел за файлом
    file_hash = message.command[1]
    if not await check_subscription(client, user_id):
        return await message.reply("⚠️ **Доступ закрыт!**\nСначала подпишись на канал проекта.", reply_markup=sub_button)

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT remote_msg_id, type FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()

    if row:
        msg_id, f_type = row
        try:
            # Копируем файл из закрытого канала-хранилища пользователю
            await client.copy_message(chat_id=message.chat.id, from_chat_id=STORAGE_CHANNEL, message_id=msg_id, reply_markup=sub_button)
        except Exception as e:
            await message.reply(f"❌ Файл не найден в хранилище. Админ, проверь канал {STORAGE_CHANNEL}")

@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def admin_upload(client, message):
    # Бот пересылает файл в @IllyaTelegram, чтобы он там жил вечно
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    
    f_hash = secrets.token_urlsafe(8)
    name = message.caption or "Файл"

    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (f_hash, sent_msg.id, "file", name))
    conn.commit()
    conn.close()

    url = f"https://t.me/plutoniumfilesBot?start={f_hash}"
    await message.reply(f"💎 **Файл сохранен в хранилище!**\n\nНазвание: `{name}`\nСсылка (нажми, чтобы скопировать):\n`{url}`")
    
    # Бэкап базы в личку админу
    try: await message.reply_document(DB_PATH, caption="📦 Бэкап базы (на случай редеплоя)")
    except: pass

@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_files(client, message):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT hash, name FROM files").fetchall()
    conn.close()
    if not rows: return await message.reply("База пуста.")
    res = "📂 **Список твоих ссылок:**\n\n" + "\n".join([f"• {n}\n`https://t.me/plutoniumfilesBot?start={h}`" for h, n in rows])
    await message.reply(res)

# --- РАССЫЛКА ---
@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    if not message.reply_to_message:
        return await message.reply("Ответь командой `/send` на любое сообщение (текст/фото), чтобы разослать его всем.")
    
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()

    count = 0
    status = await message.reply(f"🚀 Рассылка началась ({len(users)} чел.)...")
    
    for (uid,) in users:
        try:
            await message.reply_to_message.copy(uid)
            count += 1
            if count % 10 == 0: await status.edit_text(f"Прогресс: {count}/{len(users)}")
            await asyncio.sleep(0.05) # Плавная отправка против бана
        except FloodWait as e: await asyncio.sleep(e.value)
        except: pass
    
    await status.edit_text(f"✅ Готово! Сообщение получили {count} пользователей.")

init_db()
print("Бот Plutonium запущен!")
app.run()
                
