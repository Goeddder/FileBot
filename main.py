import os
import sqlite3
import secrets
import asyncio
import logging
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait, MessageIdInvalid

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
API_ID = 39522849
API_HASH = "26909eddad0be2400fb765fad0e267f8"
BOT_TOKEN = "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw"
ADMIN_ID = 1471307057  
CHANNEL_URL = "https://t.me/OfficialPlutonium"
CHANNEL_ID = "@OfficialPlutonium"
STORAGE_CHANNEL = "@IllyaTelegram"
# ================================

# ВАЖНО: используем имя сессии, которое точно запишется
app = Client(
    "plutonium_bot_session",
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN,
    in_memory=False  # сессия сохранится на диск
)

# ---------- БАЗА ДАННЫХ ----------
DB_PATH = "files.db"
BACKUP_ID_FILE = "backup_id.txt"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            hash TEXT PRIMARY KEY,
            msg_id INTEGER,
            name TEXT,
            added_at TEXT
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
    logger.info("✅ База данных готова")

def save_user(user_id, username):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR IGNORE INTO users (user_id, username, joined_at) VALUES (?, ?, ?)",
                    (user_id, username, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя: {e}")

def save_file(hash, msg_id, name):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO files (hash, msg_id, name, added_at) VALUES (?, ?, ?, ?)",
                (hash, msg_id, name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

def get_file(hash):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT msg_id, name FROM files WHERE hash = ?", (hash,)).fetchone()
    conn.close()
    return row

def get_all_files():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT hash, name FROM files ORDER BY added_at DESC").fetchall()
    conn.close()
    return rows

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return rows

# ---------- БЭКАП БАЗЫ ----------
def save_backup_id(msg_id):
    with open(BACKUP_ID_FILE, "w") as f:
        f.write(str(msg_id))

def load_backup_id():
    try:
        with open(BACKUP_ID_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return None

async def restore_db_from_channel():
    backup_id = load_backup_id()
    if not backup_id:
        return False
    
    try:
        msg = await app.get_messages(STORAGE_CHANNEL, backup_id)
        if msg and msg.document:
            await app.download_media(msg, file_name=DB_PATH)
            logger.info("✅ База восстановлена из канала")
            return True
    except Exception as e:
        logger.error(f"Ошибка восстановления: {e}")
    return False

async def backup_db_to_channel():
    try:
        old_id = load_backup_id()
        if old_id:
            try:
                await app.delete_messages(STORAGE_CHANNEL, old_id)
            except:
                pass
        
        msg = await app.send_document(STORAGE_CHANNEL, DB_PATH, 
                                     caption=f"🔄 Бэкап БД {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        save_backup_id(msg.id)
        logger.info("✅ База сохранена в канал")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка бэкапа: {e}")
        return False

# ---------- ПРОВЕРКА ПОДПИСКИ ----------
async def check_sub(client, user_id):
    try:
        member = await client.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ["left", "kicked"]
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return True  # временно пускаем

# ---------- КОМАНДА СТАРТ ----------
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    save_user(user_id, username)
    logger.info(f"Пользователь {user_id} запустил бота")

    sub_button = InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Канал Plutonium", url=CHANNEL_URL)
    ]])

    if len(message.command) == 1:
        await message.reply(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"🤖 Я бот Plutonium. Перейди по ссылке, чтобы получить файл.",
            reply_markup=sub_button
        )
        return

    file_hash = message.command[1]
    
    if not await check_sub(client, user_id):
        await message.reply("⚠️ Для доступа подпишись на канал!", reply_markup=sub_button)
        return

    file_info = get_file(file_hash)
    if not file_info:
        await message.reply("❌ Файл не найден")
        return

    msg_id, name = file_info
    try:
        await client.copy_message(
            chat_id=message.chat.id,
            from_chat_id=STORAGE_CHANNEL,
            message_id=msg_id,
            caption=f"📁 **{name}**",
            reply_markup=sub_button
        )
    except MessageIdInvalid:
        await message.reply("❌ Файл утерян, сообщи админу")

# ---------- ДОБАВЛЕНИЕ ФАЙЛА ----------
@app.on_message(filters.command("addfile") & filters.user(ADMIN_ID))
async def addfile_cmd(client, message):
    await message.reply("📤 Отправь файл (документ, фото или видео).\nВ подписи укажи название (необязательно).")

@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def handle_file(client, message):
    if message.document:
        name = message.caption or message.document.file_name or "Документ"
    elif message.video:
        name = message.caption or message.video.file_name or "Видео"
    else:
        name = message.caption or "Фото"

    sent = await message.copy(chat_id=STORAGE_CHANNEL)
    
    file_hash = secrets.token_urlsafe(8)
    save_file(file_hash, sent.id, name)

    await backup_db_to_channel()

    bot_me = await client.get_me()
    url = f"https://t.me/{bot_me.username}?start={file_hash}"
    
    await message.reply(
        f"✅ **Файл сохранён!**\n\n"
        f"📁 {name}\n"
        f"🔗 `{url}`",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📢 Канал с файлами", url=f"https://t.me/{STORAGE_CHANNEL[1:]}")
        ]])
    )

# ---------- СПИСОК ФАЙЛОВ ----------
@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_cmd(client, message):
    files = get_all_files()
    if not files:
        await message.reply("📭 Нет файлов")
        return

    text = "📂 **Все файлы:**\n\n"
    bot_me = await client.get_me()
    for h, name in files:
        url = f"https://t.me/{bot_me.username}?start={h}"
        text += f"📁 {name}\n`{url}`\n\n"
        if len(text) > 3500:
            await message.reply(text)
            text = ""
    
    if text:
        await message.reply(text)

# ---------- РАССЫЛКА ----------
@app.on_message(filters.command("send") & filters.user(ADMIN_ID))
async def send_cmd(client, message):
    if not message.reply_to_message:
        await message.reply("❌ Ответь этой командой на сообщение для рассылки")
        return

    users = get_all_users()
    if not users:
        await message.reply("📭 Нет пользователей")
        return

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
        except Exception as e:
            logger.error(f"Ошибка отправки {uid}: {e}")

    await status.edit_text(f"✅ Рассылка завершена!\n✅ {success} / ❌ {len(users)-success}")

# ---------- ПОЛЬЗОВАТЕЛИ ----------
@app.on_message(filters.command("users") & filters.user(ADMIN_ID))
async def users_cmd(client, message):
    users = get_all_users()
    await message.reply(f"👥 Всего пользователей: {len(users)}")

# ---------- ПОМОЩЬ ----------
@app.on_message(filters.command("help") & filters.user(ADMIN_ID))
async def help_cmd(client, message):
    text = """
**👑 Админ-команды:**

📁 **Файлы:**
/addfile - добавить новый файл
/list - список всех файлов

👥 **Пользователи:**
/users - статистика
/send - рассылка (ответом на сообщение)

🔄 **База:**
/backup - ручной бэкап в канал
/restore - восстановить из канала

ℹ️ **Другое:**
/help - это меню
"""
    await message.reply(text)

# ---------- БЭКАП (ручной) ----------
@app.on_message(filters.command("backup") & filters.user(ADMIN_ID))
async def backup_cmd(client, message):
    if await backup_db_to_channel():
        await message.reply("✅ База сохранена в канал")
    else:
        await message.reply("❌ Ошибка сохранения")

@app.on_message(filters.command("restore") & filters.user(ADMIN_ID))
async def restore_cmd(client, message):
    if await restore_db_from_channel():
        await message.reply("✅ База восстановлена из канала")
    else:
        await message.reply("❌ Бэкап не найден")

# ---------- ЗАПУСК ----------
async def main():
    print("🚀 Запуск бота...")
    
    # Добавляем обработчик реконнекта
    while True:
        try:
            await app.start()
            break
        except FloodWait as e:
            wait_time = e.value
            print(f"⏳ Flood wait: {wait_time} секунд")
            await asyncio.sleep(wait_time)
    
    print("✅ Клиент запущен")
    
    # Проверяем, что бот видит команды
    me = await app.get_me()
    print(f"✅ Бот: @{me.username}")
    
    # Восстанавливаем базу
    if await restore_db_from_channel():
        print("✅ База восстановлена из канала")
    else:
        init_db()
        print("✅ Создана новая база")
    
    print(f"📢 Канал подписки: {CHANNEL_ID}")
    print(f"💾 Канал-хранилище: {STORAGE_CHANNEL}")
    print("="*40)
    print("🤖 Бот готов к работе!")
    
    # Держим бота запущенным
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
