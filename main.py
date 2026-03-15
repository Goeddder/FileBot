import os
import sqlite3
import secrets
import subprocess
import sys
import asyncio
import io
from datetime import datetime, timedelta
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
STORAGE_CHANNEL = "@IllyaTelegram"

DB_PATH = "files.db"
BACKUP_MSG_ID_FILE = "backup_id.txt"

app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ==========

def get_backup_msg_id():
    """Читает ID бэкапа из файла"""
    try:
        with open(BACKUP_MSG_ID_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return None

def save_backup_msg_id(msg_id):
    """Сохраняет ID бэкапа в файл"""
    with open(BACKUP_MSG_ID_FILE, "w") as f:
        f.write(str(msg_id))

async def download_db_from_channel():
    """Скачивает базу данных из канала"""
    backup_id = get_backup_msg_id()
    if not backup_id:
        return False
    
    try:
        msg = await app.get_messages(STORAGE_CHANNEL, backup_id)
        if msg and msg.document and msg.document.file_name == "files.db":
            file = await app.download_media(msg, in_memory=True)
            with open(DB_PATH, 'wb') as f:
                f.write(file.getbuffer())
            print(f"✅ База загружена из канала (ID: {backup_id})")
            return True
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
    return False

async def upload_db_to_channel():
    """Сохраняет базу данных в канал"""
    try:
        # Удаляем старый бэкап если есть
        old_id = get_backup_msg_id()
        if old_id:
            try:
                await app.delete_messages(STORAGE_CHANNEL, old_id)
            except:
                pass
        
        # Отправляем новую базу
        msg = await app.send_document(
            STORAGE_CHANNEL, 
            DB_PATH, 
            caption=f"📦 Бэкап БД {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        save_backup_msg_id(msg.id)
        print(f"✅ База сохранена в канал (ID: {msg.id})")
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return False

def init_db():
    """Создает новую базу данных"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            hash TEXT PRIMARY KEY, 
            remote_msg_id INTEGER, 
            name TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            joined_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Новая база создана")

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

async def check_subscription(client, user_id):
    """Проверяет подписку на канал"""
    try:
        member = await client.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ["left", "kicked"]
    except UserNotParticipant:
        return False
    except:
        return True

def save_user(user_id, username=None):
    """Сохраняет пользователя"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, joined_at) VALUES (?, ?, ?)",
        (user_id, username, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    conn.close()

# ========== ОБРАБОТЧИКИ ==========

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    save_user(user_id, username)

    sub_button = InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Канал Plutonium", url=CHANNEL_URL)
    ]])

    if len(message.command) == 1:
        return await message.reply(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"Я бот-архив проекта **Plutonium**.",
            reply_markup=sub_button
        )

    file_hash = message.command[1]
    
    if not await check_subscription(client, user_id):
        return await message.reply(
            "⚠️ **Доступ закрыт!**\nСначала подпишись на канал.",
            reply_markup=sub_button
        )

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
            await message.reply("❌ Файл не найден в хранилище")
    else:
        await message.reply("❌ Ссылка недействительна")

# ========== ЗАГРУЗКА ФАЙЛОВ ==========

@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def admin_upload(client, message):
    # Отправляем файл в канал-хранилище
    sent_msg = await message.copy(chat_id=STORAGE_CHANNEL)
    
    f_hash = secrets.token_urlsafe(8)
    
    if message.document:
        name = message.document.file_name or "Документ"
    elif message.video:
        name = message.video.file_name or "Видео"
    else:
        name = message.caption or "Фото"

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO files (hash, remote_msg_id, name, created_at) VALUES (?, ?, ?, ?)",
        (f_hash, sent_msg.id, name, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    )
    conn.commit()
    conn.close()

    bot_username = (await client.get_me()).username
    url = f"https://t.me/{bot_username}?start={f_hash}"
    
    await message.reply(
        f"💎 **Файл сохранен!**\n\n"
        f"📁 **Название:** {name}\n"
        f"🔗 **Ссылка:**\n`{url}`"
    )
    
    # Сохраняем базу в канал
    await upload_db_to_channel()

# ========== АДМИН-КОМАНДЫ ==========

@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_files(client, message):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT hash, name, created_at FROM files ORDER BY created_at DESC").fetchall()
    conn.close()
    
    if not rows:
        return await message.reply("📭 База пуста.")
    
    text = "📂 **Все файлы:**\n\n"
    bot_username = (await client.get_me()).username
    
    for h, name, created in rows:
        url = f"https://t.me/{bot_username}?start={h}"
        text += f"📁 {name}\n`{url}`\n📅 {created[:10]}\n\n"
        
        if len(text) > 3500:
            await message.reply(text)
            text = ""
    
    if text:
        await message.reply(text)

@app.on_message(filters.command("users") & filters.user(ADMIN_ID))
async def users_stats(client, message):
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    new_today = conn.execute(
        "SELECT COUNT(*) FROM users WHERE joined_at > ?",
        (yesterday,)
    ).fetchone()[0]
    
    conn.close()
    
    await message.reply(
        f"👥 **Статистика пользователей:**\n\n"
        f"📊 Всего: {total}\n"
        f"🆕 За 24ч: {new_today}"
    )

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
    
    await status.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"✅ Получили: {success}\n"
        f"❌ Не доставлено: {len(users)-success}"
    )

@app.on_message(filters.command("backup") & filters.user(ADMIN_ID))
async def manual_backup(client, message):
    if await upload_db_to_channel():
        await message.reply("✅ База данных сохранена в канал!")
    else:
        await message.reply("❌ Ошибка сохранения.")

@app.on_message(filters.command("restore") & filters.user(ADMIN_ID))
async def manual_restore(client, message):
    if await download_db_from_channel():
        await message.reply("✅ База данных восстановлена из канала!")
    else:
        await message.reply("❌ Не найдено бэкапа. Сначала сделай /backup")

@app.on_message(filters.command("help") & filters.user(ADMIN_ID))
async def help_cmd(client, message):
    help_text = """
**👑 Админ-команды:**

📁 **Файлы:**
/list - список всех файлов
/backup - сохранить базу в канал
/restore - восстановить базу из канала

👥 **Пользователи:**
/users - статистика пользователей
/send - рассылка (ответом на сообщение)

ℹ️ **Другое:**
/help - это сообщение
"""
    await message.reply(help_text)

# ========== ЗАПУСК ==========

async def main():
    print("🚀 Запуск бота...")
    
    await app.start()
    print("✅ Клиент Telegram запущен")
    
    # Пробуем загрузить базу
    if await download_db_from_channel():
        print("✅ База загружена из канала")
    else:
        init_db()
        await upload_db_to_channel()
        print("✅ Создана новая база")
    
    print("\n" + "="*40)
    print("🤖 Бот успешно запущен!")
    print(f"📢 Канал подписки: {CHANNEL_ID}")
    print(f"💾 Канал-хранилище: {STORAGE_CHANNEL}")
    print("="*40 + "\n")
    
    # Бесконечное ожидание
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
