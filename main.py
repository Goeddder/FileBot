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

# КАНАЛ ДЛЯ ПОДПИСКИ
REQUIRED_CHANNEL = "@OfficialPlutonium"
REQUIRED_CHANNEL_URL = "https://t.me/OfficialPlutonium"

# КАНАЛ-ХРАНИЛИЩЕ
STORAGE_CHANNEL = "@IllyaTelegram"
STORAGE_CHANNEL_URL = "https://t.me/IllyaTelegram"

DB_PATH = "files.db"

app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Прогресс отправки
async def progress(current, total, message, start_time):
    percent = (current * 100) / total
    elapsed = time.time() - start_time
    if int(percent) % 20 == 0:
        try:
            await message.edit_text(f"🚀 Отправка: {percent:.1f}%\n⏱ Время: {elapsed:.1f} сек.")
        except: pass

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            hash TEXT PRIMARY KEY, 
            file_id TEXT, 
            type TEXT, 
            name TEXT,
            description TEXT,
            storage_message_id INTEGER
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, joined_date TEXT)")
    conn.commit()
    conn.close()
    
    # Проверка базы при запуске
    conn = sqlite3.connect(DB_PATH)
    users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    conn.close()
    print(f"📊 База данных: {users_count} пользователей, {files_count} файлов")

# Проверка подписки
async def check_subscription(client, user_id):
    try:
        member = await client.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status not in ["left", "kicked"]
    except UserNotParticipant:
        return False
    except Exception as e:
        print(f"Subscription check error: {e}")
        return False

# --- ОБРАБОТЧИКИ ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # Сохраняем пользователя в БД
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO users (user_id, joined_date) VALUES (?, datetime('now'))", (user_id,))
    conn.commit()
    conn.close()
    
    # Кнопка на канал (всегда одна)
    channel_button = InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Канал Plutonium", url=REQUIRED_CHANNEL_URL)
    ]])

    # Если это просто старт без параметров
    if len(message.command) == 1:
        welcome_text = (
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "🤖 Я — бот для скачивания файлов Plutonium.\n"
            "Чтобы получить файлы, подпишись на канал и перейди по ссылке."
        )
        return await message.reply(welcome_text, reply_markup=channel_button)

    # Если есть параметр (попытка получить файл)
    file_hash = message.command[1]
    
    # Проверка подписки
    is_subscribed = await check_subscription(client, user_id)
    if not is_subscribed:
        return await message.reply(
            "⚠️ **Доступ ограничен!**\n\nДля получения файла нужно подписаться на @OfficialPlutonium.",
            reply_markup=channel_button
        )

    # Поиск файла
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT file_id, type, name, description FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()
    
    if row:
        f_id, f_type, f_name, f_desc = row
        start_time = time.time()
        
        # Формируем описание
        caption = f"📁 **{f_name}**"
        if f_desc and f_desc != "None" and f_desc.strip():
            caption += f"\n\n📝 {f_desc}"
        
        status_msg = await message.reply("⏳ Загружаю файл...")
        
        try:
            if f_type == 'photo':
                await message.reply_photo(f_id, caption=caption, reply_markup=channel_button)
            elif f_type == 'video':
                await message.reply_video(f_id, caption=caption, reply_markup=channel_button,
                                          progress=progress, progress_args=(status_msg, start_time))
            else:
                await message.reply_document(f_id, caption=caption, reply_markup=channel_button,
                                            progress=progress, progress_args=(status_msg, start_time))
            
            total_time = time.time() - start_time
            await status_msg.edit_text(f"✅ Файл доставлен за {total_time:.1f} сек.")
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка: {e}")
    else:
        await message.reply("❌ Файл не найден или ссылка недействительна.")

# --- КОМАНДА /list (ДЛЯ АДМИНА) ---
@app.on_message(filters.command("list") & filters.user(ADMIN_ID))
async def list_files(client, message):
    print(f"🔍 /list вызвана админом {message.from_user.id}")
    
    conn = sqlite3.connect(DB_PATH)
    files = conn.execute("SELECT hash, name, description FROM files ORDER BY rowid DESC").fetchall()
    conn.close()
    
    if not files:
        await message.reply("📭 База пуста.")
        return
    
    text = "📂 **Список файлов:**\n\n"
    for h, name, desc in files:
        url = f"https://t.me/{(await client.get_me()).username}?start={h}"
        text += f"🔹 **{name}**\n"
        if desc and desc.strip():
            text += f"{desc}\n"
        text += f"{url}\n\n"
        
        if len(text) > 3500:
            await message.reply(text)
            text = "📂 **Продолжение:**\n\n"
    
    if text:
        await message.reply(text)

# --- КОМАНДА /broadcast (ДЛЯ АДМИНА) ---
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_start(client, message):
    print(f"📢 /broadcast вызвана админом {message.from_user.id}")
    
    await message.reply(
        "📢 **Режим рассылки**\n\n"
        "Отправь сообщение для рассылки всем пользователям.\n"
        "❌ /cancel - отмена"
    )
    app.broadcast_mode = True

@app.on_message(filters.user(ADMIN_ID) & ~filters.command("cancel") & ~filters.command("broadcast") & ~filters.command("list"))
async def broadcast_send(client, message):
    if not hasattr(app, 'broadcast_mode') or not app.broadcast_mode:
        return
    
    print(f"📨 Начинаю рассылку...")
    
    conn = sqlite3.connect(DB_PATH)
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    
    if not users:
        await message.reply("📭 Нет пользователей для рассылки.")
        app.broadcast_mode = False
        return
    
    status_msg = await message.reply(f"⏳ Рассылка {len(users)} пользователям...")
    
    success = 0
    failed = 0
    
    for i, (user_id,) in enumerate(users, 1):
        try:
            await message.copy(user_id)
            success += 1
        except Exception as e:
            failed += 1
            print(f"❌ Ошибка отправки {user_id}: {e}")
        
        if i % 10 == 0:
            await status_msg.edit_text(f"⏳ Прогресс: {i}/{len(users)} (✅ {success} | ❌ {failed})")
        
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(f"✅ Рассылка завершена!\n✅ Успешно: {success}\n❌ Ошибок: {failed}")
    app.broadcast_mode = False

@app.on_message(filters.command("cancel") & filters.user(ADMIN_ID))
async def broadcast_cancel(client, message):
    if hasattr(app, 'broadcast_mode'):
        app.broadcast_mode = False
        await message.reply("❌ Рассылка отменена")
        print("❌ Рассылка отменена")

# --- КОМАНДА /admin (ДЛЯ АДМИНА) ---
@app.on_message(filters.command("admin") & filters.user(ADMIN_ID))
async def admin_panel(client, message):
    conn = sqlite3.connect(DB_PATH)
    files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    
    text = (
        f"👑 **Админ-панель**\n\n"
        f"📁 Файлов: {files_count}\n"
        f"👥 Пользователей: {users_count}\n\n"
        f"**Команды:**\n"
        f"/list - список файлов\n"
        f"/broadcast - рассылка\n"
        f"/stats - статистика\n"
        f"/del [хеш] - удалить файл"
    )
    await message.reply(text)

# --- КОМАНДА /stats (ДЛЯ АДМИНА) ---
@app.on_message(filters.command("stats") & filters.user(ADMIN_ID))
async def stats(client, message):
    conn = sqlite3.connect(DB_PATH)
    files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    photos = conn.execute("SELECT COUNT(*) FROM files WHERE type='photo'").fetchone()[0]
    videos = conn.execute("SELECT COUNT(*) FROM files WHERE type='video'").fetchone()[0]
    docs = conn.execute("SELECT COUNT(*) FROM files WHERE type='doc'").fetchone()[0]
    conn.close()
    
    text = (
        f"📊 **Статистика**\n\n"
        f"👥 Пользователей: {users_count}\n"
        f"📁 Всего файлов: {files_count}\n"
        f"├ Фото: {photos}\n"
        f"├ Видео: {videos}\n"
        f"└ Документы: {docs}"
    )
    await message.reply(text)

# --- КОМАНДА /del (ДЛЯ АДМИНА) ---
@app.on_message(filters.command("del") & filters.user(ADMIN_ID))
async def delete_file(client, message):
    try:
        file_hash = message.command[1]
        
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM files WHERE hash = ?", (file_hash,))
        conn.commit()
        affected = conn.total_changes
        conn.close()
        
        if affected:
            await message.reply(f"✅ Файл {file_hash} удален")
        else:
            await message.reply("❌ Файл не найден")
    except IndexError:
        await message.reply("❌ Использование: /del [хеш]")

# --- ЗАГРУЗКА ФАЙЛА АДМИНОМ (БЕЗ ЛИШНИХ СООБЩЕНИЙ) ---
@app.on_message((filters.document | filters.video | filters.photo) & filters.user(ADMIN_ID))
async def admin_upload(client, message):
    # Сохраняем данные файла
    if message.photo:
        f_id = message.photo.file_id
        f_type = 'photo'
        f_name = message.caption or "Фото"
    elif message.video:
        f_id = message.video.file_id
        f_type = 'video'
        f_name = message.caption or "Видео"
    else:
        f_id = message.document.file_id
        f_type = 'doc'
        f_name = message.document.file_name or "Документ"
    
    # Сразу просим описание (без лишних сообщений)
    await message.reply(
        f"📝 **Файл получен:** {f_name}\n\n"
        "✍️ **Отправь описание для файла**\n"
        "(или отправь /skip чтобы пропустить):"
    )
    
    # Сохраняем временно
    app.temp_file_data = {
        "f_id": f_id,
        "f_type": f_type,
        "f_name": f_name
    }

@app.on_message(filters.text & filters.user(ADMIN_ID) & ~filters.command("start") & ~filters.command("list") & ~filters.command("broadcast") & ~filters.command("admin") & ~filters.command("stats") & ~filters.command("del") & ~filters.command("cancel"))
async def get_description(client, message):
    if not hasattr(app, 'temp_file_data'):
        return
    
    desc = message.text if message.text != "/skip" else ""
    
    try:
        # Сохраняем в канал-хранилище
        if app.temp_file_data["f_type"] == 'photo':
            storage_msg = await client.send_photo(STORAGE_CHANNEL, app.temp_file_data["f_id"], 
                                                  caption=app.temp_file_data['f_name'])
        elif app.temp_file_data["f_type"] == 'video':
            storage_msg = await client.send_video(STORAGE_CHANNEL, app.temp_file_data["f_id"], 
                                                  caption=app.temp_file_data['f_name'])
        else:
            storage_msg = await client.send_document(STORAGE_CHANNEL, app.temp_file_data["f_id"], 
                                                     caption=app.temp_file_data['f_name'])
        
        # Генерируем хеш
        f_hash = secrets.token_urlsafe(8)
        
        # Сохраняем в БД
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO files (hash, file_id, type, name, description, storage_message_id) VALUES (?, ?, ?, ?, ?, ?)",
            (f_hash, app.temp_file_data["f_id"], app.temp_file_data["f_type"], 
             app.temp_file_data["f_name"], desc, storage_msg.id)
        )
        conn.commit()
        conn.close()
        
        share_url = f"https://t.me/{(await client.get_me()).username}?start={f_hash}"
        
        # Отправляем ТОЛЬКО ссылку (без кнопок)
        await message.reply(
            f"✅ **Файл сохранен!**\n\n"
            f"📁 **Название:** {app.temp_file_data['f_name']}\n"
            f"📝 **Описание:** {desc if desc else '—'}\n\n"
            f"🔗 **Ссылка:**\n`{share_url}`"
        )
        
        del app.temp_file_data
        
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

# Инициализация
init_db()
print("--- БОТ ЗАПУЩЕН ---")
print(f"Канал подписки: {REQUIRED_CHANNEL}")
print(f"Канал-хранилище: {STORAGE_CHANNEL}")
print(f"Админ ID: {ADMIN_ID}")
print("✅ Команды: /admin, /list, /broadcast, /stats, /del")

app.run()
