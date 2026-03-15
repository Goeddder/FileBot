import os
import sqlite3
import secrets
import subprocess
import sys
import time
import asyncio
import io
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait, MessageIdInvalid

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
CHANNEL_ID = "@OfficialPlutonium"
STORAGE_CHANNEL = "@IllyaTelegram"  # Бот должен быть админом!

# ID сообщения с базой данных в канале (если есть)
DB_BACKUP_MSG_ID = None

DB_PATH = "files.db"

app = Client("plutonium_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- ФУНКЦИЯ ЗАГРУЗКИ БАЗЫ ИЗ КАНАЛА ---
async def load_db_from_channel():
    global DB_BACKUP_MSG_ID
    try:
        # Ищем последнее сообщение с файлом базы данных
        async for msg in app.search_messages(STORAGE_CHANNEL, query="db_backup"):
            if msg.document and msg.document.file_name == "files.db":
                DB_BACKUP_MSG_ID = msg.id
                # Скачиваем базу в память
                file = await app.download_media(msg, in_memory=True)
                with open(DB_PATH, 'wb') as f:
                    f.write(file.getbuffer())
                print(f"✅ База данных восстановлена из канала (ID сообщения: {DB_BACKUP_MSG_ID})")
                return True
    except Exception as e:
        print(f"❌ Не удалось загрузить базу из канала: {e}")
    return False

# --- ФУНКЦИЯ СОХРАНЕНИЯ БАЗЫ В КАНАЛ ---
async def backup_db_to_channel():
    global DB_BACKUP_MSG_ID
    try:
        # Удаляем старый бэкап если есть
        if DB_BACKUP_MSG_ID:
            try:
                await app.delete_messages(STORAGE_CHANNEL, DB_BACKUP_MSG_ID)
            except:
                pass
        
        # Отправляем новую базу
        msg = await app.send_document(
            STORAGE_CHANNEL, 
            DB_PATH, 
            caption=f"db_backup {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        DB_BACKUP_MSG_ID = msg.id
        print(f"✅ База данных сохранена в канал (ID сообщения: {DB_BACKUP_MSG_ID})")
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения базы: {e}")
        return False

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
    except UserNotParticipant: 
        return False
    except: 
        return True

# --- ОБРАБОТЧИКИ ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # Регистрация юзера
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    sub_button = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Канал Plutonium", url=CHANNEL_URL)]])

    if len(message.command) == 1:
        return await message.reply(
            f"👋 Привет, {message.from_user.first_name}!\n\nЯ бот-архив проекта **Plutonium**. Подпишись на канал, чтобы скачивать файлы.",
            reply_markup=sub_button
        )

    file_hash = message.command[1]
    if not await check_subscription(client, user_id):
        return await message.reply("⚠️ **Доступ закрыт!**\nСначала подпишись на канал.", reply_markup=sub_button)

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT remote_msg_id, name FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()

    if row:
        msg_id, name = row
        try:
            await client.copy_message(
                chat_id=message.chat.id, 
                from_chat_id=STORAGE_CHANNEL, 
                message_id=msg_id, 
                caption=f"📁 **{name}**",
                reply_markup=sub_button
            )
        except MessageIdInvalid:
            await message.reply(f"❌ Файл не найден в хранилище. Сообщи админу.")
    else:
        await message.reply("❌ Ссылка недействительна.")

@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def admin_upload(client, message):
    # Отправляем в канал-хранилище
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    
    f_hash = secrets.token_urlsafe(8)
    name = message.caption or (message.document.file_name if message.document else "Файл")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files VALUES (?, ?, ?, ?)", 
                (f_hash, sent_msg.id, "file", name))
    conn.commit()
    conn.close()

    url = f"https://t.me/{(await client.get_me()).username}?start={f_hash}"
    await message.reply(
        f"💎 **Файл сохранен!**\n\n📁 {name}\n🔗 {url}"
    )
    
    # Сохраняем базу в канал
    await backup_db_to_channel()

@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_files(client, message):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT hash, name FROM files").fetchall()
    conn.close()
    
    if not rows: 
        return await message.reply("📭 База пуста.")
    
    text = "📂 **Твои файлы:**\n\n"
    for h, name in rows:
        url = f"https://t.me/{(await client.get_me()).username}?start={h}"
        text += f"📁 {name}\n`{url}`\n\n"
        
        if len(text) > 3500:
            await message.reply(text)
            text = ""
    
    if text:
        await message.reply(text)

@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def broadcast(client, message):
    if not message.reply_to_message:
        return await message.reply("❌ Ответь командой `/send` на сообщение для рассылки.")
    
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()

    if not users:
        return await message.reply("📭 Нет пользователей в базе.")

    status = await message.reply(f"🚀 Рассылка {len(users)} пользователям...")
    
    success = 0
    for i, (uid,) in enumerate(users, 1):
        try:
            await message.reply_to_message.copy(uid)
            success += 1
            if i % 10 == 0:
                await status.edit_text(f"⏳ Прогресс: {i}/{len(users)} (✅ {success})")
            await asyncio.sleep(0.05)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except:
            pass
    
    await status.edit_text(f"✅ Рассылка завершена!\n✅ Получили: {success}\n❌ Не доставлено: {len(users)-success}")

@app.on_message(filters.command("restore") & filters.user(ADMIN_ID))
async def restore_db(client, message):
    if await load_db_from_channel():
        await message.reply("✅ База данных восстановлена из канала!")
    else:
        await message.reply("❌ Не удалось найти бэкап в канале.")

@app.on_message(filters.command("backup") & filters.user(ADMIN_ID))
async def backup_now(client, message):
    if await backup_db_to_channel():
        await message.reply("✅ База данных сохранена в канал!")
    else:
        await message.reply("❌ Ошибка сохранения.")

@app.on_message(filters.command("users") & filters.user(ADMIN_ID))
async def users_count(client, message):
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    await message.reply(f"👥 Всего пользователей: {count}")

# --- ЗАПУСК ---
async def main():
    # Пробуем загрузить базу из канала
    if await load_db_from_channel():
        print("✅ База загружена из канала")
    else:
        # Если нет бэкапа — создаем новую
        init_db()
        print("✅ Создана новая база данных")
    
    print("🤖 Бот запущен!")
    print(f"📢 Канал подписки: {CHANNEL_ID}")
    print(f"💾 Канал-хранилище: {STORAGE_CHANNEL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
