import asyncio
import sqlite3
import secrets
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ========== ТВОИ ДАННЫЕ ==========
TOKEN = "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw"
ADMIN_ID = 1471307057
CHANNEL_URL = "https://t.me/OfficialPlutonium"
# ================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------- ТВОЯ БАЗА (КАК БЫЛО) ----------
def init_db():
    conn = sqlite3.connect('files.db')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            hash TEXT PRIMARY KEY,
            file_id TEXT,
            file_name TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()
    logger.info("✅ База готова")

def save_user(user_id):
    conn = sqlite3.connect('files.db')
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def save_file(file_hash, file_id, file_name):
    conn = sqlite3.connect('files.db')
    conn.execute("INSERT INTO files (hash, file_id, file_name) VALUES (?, ?, ?)",
                (file_hash, file_id, file_name))
    conn.commit()
    conn.close()

def get_file(file_hash):
    conn = sqlite3.connect('files.db')
    row = conn.execute("SELECT file_id, file_name FROM files WHERE hash = ?", (file_hash,)).fetchone()
    conn.close()
    return row

def get_all_files():
    conn = sqlite3.connect('files.db')
    rows = conn.execute("SELECT hash, file_name FROM files").fetchall()
    conn.close()
    return rows

def get_all_users():
    conn = sqlite3.connect('files.db')
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return rows

# ---------- ТВОЙ СТАРТ ----------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)

    channel_btn = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Канал Plutonium", url=CHANNEL_URL)]
    ])

    if len(message.text.split()) == 1:
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\nЯ бот Plutonium.",
            reply_markup=channel_btn
        )
        return

    file_hash = message.text.split()[1]
    file_info = get_file(file_hash)

    if not file_info:
        await message.answer("❌ Файл не найден")
        return

    file_id, file_name = file_info
    await message.answer_document(
        document=file_id,
        caption=f"📁 {file_name}",
        reply_markup=channel_btn
    )

# ---------- ТВОЕ ДОБАВЛЕНИЕ ФАЙЛА + БЭКАП ----------
@dp.message(Command("addfile"))
async def addfile_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📤 Отправь мне файл")

@dp.message(F.document)
async def get_file_from_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    file_id = message.document.file_id
    file_name = message.document.file_name or "файл"

    file_hash = secrets.token_urlsafe(8)
    save_file(file_hash, file_id, file_name)

    # ---------- БЭКАП ТЕБЕ В ЛИЧКУ ----------
    with open('files.db', 'rb') as f:
        await bot.send_document(
            chat_id=ADMIN_ID,
            document=FSInputFile('files.db'),
            caption=f"📦 Бэкап после добавления {file_name}"
        )

    bot_me = await bot.get_me()
    url = f"https://t.me/{bot_me.username}?start={file_hash}"
    await message.answer(f"✅ Файл сохранён!\n🔗 {url}")

# ---------- ВОССТАНОВЛЕНИЕ ----------
@dp.message(Command("restore"))
async def restore_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📤 Отправь мне файл files.db")

@dp.message(F.document)
async def handle_restore(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if message.document.file_name != "files.db":
        await message.answer("❌ Нужен файл files.db")
        return

    file = await bot.download_file(message.document.file_id)
    with open('files.db', 'wb') as f:
        f.write(file.getbuffer())

    await message.answer("✅ База восстановлена!")

# ---------- ТВОЙ ЛИСТ ----------
@dp.message(Command("list"))
async def list_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    files = get_all_files()
    if not files:
        await message.answer("📭 Нет файлов")
        return

    bot_me = await bot.get_me()
    text = "📂 Файлы:\n\n"
    for h, name in files:
        text += f"📁 {name}\nhttps://t.me/{bot_me.username}?start={h}\n\n"

    await message.answer(text)

# ---------- ТВОЯ РАССЫЛКА ----------
@dp.message(Command("send"))
async def send_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message:
        await message.answer("❌ Ответь на сообщение")
        return

    users = get_all_users()
    if not users:
        await message.answer("📭 Нет пользователей")
        return

    status = await message.answer(f"📢 Рассылка {len(users)} пользователям...")
    success = 0
    for uid in users:
        try:
            await message.reply_to_message.copy(uid[0])
            success += 1
            if success % 10 == 0:
                await status.edit_text(f"⏳ Прогресс: {success}/{len(users)}")
            await asyncio.sleep(0.05)
        except:
            pass

    await status.edit_text(f"✅ Разослано: {success}/{len(users)}")

# ---------- ТВОЙ ЗАПУСК ----------
async def main():
    init_db()
    await bot.delete_webhook()
    logger.info("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
