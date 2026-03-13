import os
import sqlite3
import secrets
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ========== ТВОИ ДАННЫЕ ==========
API_ID = 39522849
API_HASH = "26909eddad0be2400fb765fad0e267f8"
BOT_TOKEN = "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw"
ADMIN_ID = 1471307057  

# КАНАЛ ДЛЯ ПОДПИСКИ
REQUIRED_CHANNEL = "@OfficialPlutonium"
REQUIRED_CHANNEL_URL = "https://t.me/OfficialPlutonium"

# КАНАЛ-ХРАНИЛИЩЕ
STORAGE_CHANNEL = "@IllyaTelegram"
# =================================

app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# База данных
def init_db():
    conn = sqlite3.connect("files.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            hash TEXT PRIMARY KEY,
            file_id TEXT,
            name TEXT,
            description TEXT
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

init_db()

# Проверка подписки
async def is_subscribed(client, user_id):
    try:
        member = await client.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except:
        return False

# Кнопка на канал
def channel_button():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Канал Plutonium", url=REQUIRED_CHANNEL_URL)
    ]])

# Сохраняем пользователя
@app.on_message(filters.private)
async def save_user(client, message):
    conn = sqlite3.connect("files.db")
    conn.execute("INSERT OR IGNORE INTO users VALUES (?)", (message.from_user.id,))
    conn.commit()
    conn.close()

# ===== КОМАНДА СТАРТ =====
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    if len(message.command) == 1:
        await message.reply(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Я бот для скачивания файлов Plutonium.\n"
            "Чтобы получить файл, перейди по ссылке.",
            reply_markup=channel_button()
        )
        return

    # Получаем файл по хешу
    file_hash = message.command[1]
    conn = sqlite3.connect("files.db")
    row = conn.execute("SELECT file_id, name, description FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()

    if not row:
        await message.reply("❌ Файл не найден")
        return

    # Проверяем подписку
    if not await is_subscribed(client, message.from_user.id):
        await message.reply(
            "⚠️ Для доступа нужно подписаться на канал!",
            reply_markup=channel_button()
        )
        return

    file_id, name, desc = row
    caption = f"📁 {name}"
    if desc:
        caption += f"\n\n{desc}"

    await message.reply_document(file_id, caption=caption, reply_markup=channel_button())

# ===== ЗАГРУЗКА ФАЙЛА (ТОЛЬКО АДМИН) =====
@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def upload_file(client, message):
    # Определяем тип и имя
    if message.document:
        file_id = message.document.file_id
        name = message.document.file_name or "документ"
    elif message.video:
        file_id = message.video.file_id
        name = message.video.file_name or "видео"
    else:  # фото
        file_id = message.photo.file_id
        name = "фото"

    # Сохраняем в канал
    await client.send_document(STORAGE_CHANNEL, file_id, caption=name)

    # Просим описание
    await message.reply(
        f"📝 Файл: {name}\n\n"
        "Отправь описание (или /skip)"
    )

    # Сохраняем временно
    app.temp_file = {
        "file_id": file_id,
        "name": name
    }

@app.on_message(filters.text & filters.user(ADMIN_ID) & ~filters.command("start"))
async def get_description(client, message):
    if not hasattr(app, "temp_file"):
        return

    desc = None if message.text == "/skip" else message.text

    # Генерируем хеш
    file_hash = secrets.token_urlsafe(8)

    # Сохраняем в БД
    conn = sqlite3.connect("files.db")
    conn.execute(
        "INSERT INTO files VALUES (?, ?, ?, ?)",
        (file_hash, app.temp_file["file_id"], app.temp_file["name"], desc)
    )
    conn.commit()
    conn.close()

    # Ссылка
    url = f"https://t.me/{(await client.get_me()).username}?start={file_hash}"

    await message.reply(f"✅ Готово!\n\n{url}")

    del app.temp_file

# ===== КОМАНДА LIST =====
@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_cmd(client, message):
    conn = sqlite3.connect("files.db")
    files = conn.execute("SELECT hash, name, description FROM files ORDER BY rowid DESC").fetchall()
    conn.close()

    if not files:
        await message.reply("📭 Нет файлов")
        return

    text = "📂 **Список файлов:**\n\n"
    for h, name, desc in files:
        url = f"https://t.me/{(await client.get_me()).username}?start={h}"
        text += f"📁 **{name}**\n"
        if desc:
            text += f"📝 {desc}\n"
        text += f"🔗 {url}\n\n"

        if len(text) > 3500:
            await message.reply(text)
            text = ""

    if text:
        await message.reply(text)

# ===== КОМАНДА BROADCAST =====
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_cmd(client, message):
    await message.reply(
        "📢 Отправь сообщение для рассылки всем пользователям\n"
        "Отправь /cancel для отмены"
    )
    app.broadcast_mode = True

@app.on_message(filters.user(ADMIN_ID) & ~filters.command("start") & ~filters.command("list") & ~filters.command("broadcast") & ~filters.command("cancel"))
async def do_broadcast(client, message):
    if not hasattr(app, "broadcast_mode") or not app.broadcast_mode:
        return

    conn = sqlite3.connect("files.db")
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()

    if not users:
        await message.reply("📭 Нет пользователей")
        app.broadcast_mode = False
        return

    status = await message.reply(f"⏳ Рассылка {len(users)} пользователям...")

    success = 0
    for uid, in users:
        try:
            await message.copy(uid)
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass

    await status.edit_text(f"✅ Разослано: {success}/{len(users)}")
    app.broadcast_mode = False

@app.on_message(filters.command("cancel") & filters.user(ADMIN_ID))
async def cancel_cmd(client, message):
    if hasattr(app, "broadcast_mode"):
        app.broadcast_mode = False
        await message.reply("❌ Отменено")

# ===== ЗАПУСК =====
print("✅ Бот запущен")
print(f"Админ ID: {ADMIN_ID}")
print("Команды: /list, /broadcast")
app.run()
