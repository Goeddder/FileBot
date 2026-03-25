import os
import sqlite3
import secrets
import asyncio
import shutil
import logging
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from pyrogram.errors import UserNotParticipant, FloodWait

# --- НАСТРОЙКИ (с твоими данными) ---
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
ADMIN_ID = int(os.environ.get("OWNER_ID", 1471307057))
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/OfficialPlutonium")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@OfficialPlutonium")
STORAGE_CHANNEL = os.environ.get("STORAGE_CHANNEL", "@IllyaTelegram")

DB_PATH = "files.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- БАЗА ДАННЫХ ---
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                hash TEXT PRIMARY KEY,
                remote_msg_id INTEGER,
                type TEXT,
                name TEXT,
                game TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                invited_by INTEGER DEFAULT 0,
                total_invites INTEGER DEFAULT 0,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()
        cursor.close()
        
        # Добавляем админа
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (ADMIN_ID, ADMIN_ID))
        self.conn.commit()
        cursor.close()
        logger.info("✅ База данных готова")
    
    def execute(self, query, params=()):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        self.conn.commit()
        cursor.close()
    
    def fetch_one(self, query, params=()):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()
        cursor.close()
        return result
    
    def fetch_all(self, query, params=()):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchall()
        cursor.close()
        return result

db = Database()

# --- КЛАВИАТУРЫ ---
def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🎮 Игры")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("🔗 Рефералка")],
        [KeyboardButton("❓ Помощь")]
    ], resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📁 Добавить чит"), KeyboardButton("📋 Список читов")],
        [KeyboardButton("👥 Пользователи"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("🧹 Очистка")],
        [KeyboardButton("💾 Бэкап"), KeyboardButton("🔙 Главное меню")]
    ], resize_keyboard=True)

def get_games_keyboard():
    games = db.fetch_all("SELECT DISTINCT game FROM files WHERE game IS NOT NULL AND game != ''")
    if not games:
        return None
    buttons = []
    for game in games:
        buttons.append([KeyboardButton(f"🎮 {game['game']}")])
    buttons.append([KeyboardButton("🔙 Главное меню")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_cheats_keyboard(game):
    cheats = db.fetch_all("SELECT name FROM files WHERE game = ?", (game,))
    if not cheats:
        return None
    buttons = []
    for cheat in cheats:
        buttons.append([KeyboardButton(f"📄 {cheat['name'][:30]}")])
    buttons.append([KeyboardButton("🔙 Назад к играм")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_subscribe_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url=CHANNEL_URL)],
        [InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data="check_sub")]
    ])

# --- ФУНКЦИИ ---
async def check_subscription(client, user_id):
    if not CHANNEL_ID:
        return True
    try:
        member = await client.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return True

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    admin = db.fetch_one("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return admin is not None

# --- КЛИЕНТ ---
app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Хранилища для ожиданий
waiting_for_file = {}
waiting_for_broadcast = {}

# --- ОБРАБОТЧИКИ ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user = message.from_user
    inviter_id = None
    
    # Рефералка
    if len(message.command) > 1:
        ref = message.command[1]
        if ref.startswith("ref_"):
            try:
                inviter_id = int(ref.split("_")[1])
                if inviter_id == user.id:
                    inviter_id = None
            except:
                pass
    
    # Сохраняем пользователя
    db.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, invited_by) VALUES (?, ?, ?, ?)",
        (user.id, user.username, user.first_name, inviter_id or 0)
    )
    
    if inviter_id and inviter_id != user.id:
        db.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter_id,))
        db.execute("INSERT INTO invites (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user.id))
    
    # Проверка подписки
    subscribed = await check_subscription(client, user.id)
    if not subscribed:
        await message.reply(
            f"🔒 Привет, {user.first_name}!\n\nПодпишись на канал для доступа к читам.",
            reply_markup=get_subscribe_keyboard()
        )
        return
    
    # Главное меню
    keyboard = get_admin_keyboard() if is_admin(user.id) else get_main_keyboard()
    user_data = db.fetch_one("SELECT total_invites FROM users WHERE user_id = ?", (user.id,))
    invites = user_data['total_invites'] if user_data else 0
    
    await message.reply(
        f"🎮 **Plutonium Cheats**\n\n"
        f"👋 Привет, {user.first_name}!\n"
        f"👥 Приглашений: {invites}\n\n"
        f"Используй кнопки:",
        reply_markup=keyboard
    )

@app.on_callback_query()
async def handle_callback(client, callback):
    if callback.data == "check_sub":
        subscribed = await check_subscription(client, callback.from_user.id)
        if subscribed:
            keyboard = get_admin_keyboard() if is_admin(callback.from_user.id) else get_main_keyboard()
            await callback.message.edit_text(
                "✅ Подписка подтверждена!\n\nИспользуй кнопки:",
                reply_markup=keyboard
            )
        else:
            await callback.answer("❌ Подпишись на канал!", show_alert=True)

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.from_user.id
    text = message.text
    
    # Рассылка
    if waiting_for_broadcast.get(user_id, False):
        if not is_admin(user_id):
            waiting_for_broadcast[user_id] = False
            return
        
        waiting_for_broadcast[user_id] = False
        users = db.fetch_all("SELECT user_id FROM users")
        
        if not users:
            await message.reply("Нет пользователей")
            return
        
        status = await message.reply(f"🚀 Рассылка на {len(users)}...")
        sent = 0
        failed = 0
        
        for i, user in enumerate(users):
            try:
                await message.copy(user['user_id'])
                sent += 1
            except:
                failed += 1
            if (i + 1) % 10 == 0:
                await status.edit_text(f"📨 {sent + failed}/{len(users)} (✅ {sent} | ❌ {failed})")
                await asyncio.sleep(0.5)
        
        await status.edit_text(f"✅ Готово!\n✅ {sent}\n❌ {failed}")
        return
    
    # Проверка подписки
    if not await check_subscription(client, user_id):
        await message.reply("🔒 Подпишись на канал!", reply_markup=get_subscribe_keyboard())
        return
    
    db.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
    
    # --- КНОПКИ ---
    if text == "🔙 Главное меню":
        keyboard = get_admin_keyboard() if is_admin(user_id) else get_main_keyboard()
        await message.reply("Главное меню:", reply_markup=keyboard)
    
    elif text == "🔙 Назад к играм":
        games_kb = get_games_keyboard()
        if games_kb:
            await message.reply("🎮 Игры:", reply_markup=games_kb)
        else:
            await message.reply("📭 Нет игр", reply_markup=get_main_keyboard())
    
    elif text == "👤 Профиль":
        user_data = db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        invites = user_data['total_invites'] if user_data else 0
        await message.reply(
            f"👤 **Профиль**\n\nID: {user_id}\nПриглашений: {invites}",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "🔗 Рефералка":
        bot = await client.get_me()
        await message.reply(
            f"🔗 **Рефералка**\n\n`https://t.me/{bot.username}?start=ref_{user_id}`",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "❓ Помощь":
        await message.reply(
            "📋 **Помощь**\n\n"
            "1. Нажми «Игры»\n"
            "2. Выбери игру\n"
            "3. Нажми на чит\n\n"
            "🔗 Рефералка - приглашай друзей",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "🎮 Игры":
        games_kb = get_games_keyboard()
        if games_kb:
            await message.reply("🎮 Выбери игру:", reply_markup=games_kb)
        else:
            await message.reply("📭 Пока нет читов", reply_markup=get_main_keyboard())
    
    elif text.startswith("🎮 "):
        game = text[3:]
        cheats_kb = get_cheats_keyboard(game)
        if cheats_kb:
            await message.reply(f"🎮 {game}\nВыбери чит:", reply_markup=cheats_kb)
        else:
            await message.reply(f"❌ Нет читов для {game}", reply_markup=get_games_keyboard())
    
    elif text.startswith("📄 "):
        cheat_name = text[3:]
        file_data = db.fetch_one("SELECT remote_msg_id, name FROM files WHERE name = ?", (cheat_name,))
        if file_data:
            try:
                await client.copy_message(user_id, STORAGE_CHANNEL, file_data['remote_msg_id'])
                await message.reply(f"✅ {file_data['name']} отправлен!", reply_markup=get_games_keyboard())
            except Exception as e:
                await message.reply(f"❌ Ошибка", reply_markup=get_games_keyboard())
        else:
            await message.reply(f"❌ Не найден", reply_markup=get_games_keyboard())
    
    # --- АДМИН КНОПКИ ---
    elif is_admin(user_id):
        if text == "📁 Добавить чит":
            waiting_for_file[user_id] = True
            await message.reply(
                "📤 Отправь файл\nВ подписи: `Название | Игра`\nПример: `Aimbot | CS2`",
                reply_markup=get_admin_keyboard()
            )
        
        elif text == "📋 Список читов":
            files = db.fetch_all("SELECT name, game FROM files ORDER BY game, name")
            if not files:
                await message.reply("Пусто", reply_markup=get_admin_keyboard())
                return
            result = "📋 **Читы:**\n"
            for f in files:
                result += f"\n🎮 {f['game']}\n  • {f['name']}"
            await message.reply(result[:4000], reply_markup=get_admin_keyboard())
        
        elif text == "👥 Пользователи":
            users = db.fetch_all("SELECT user_id, first_name, total_invites FROM users ORDER BY total_invites DESC")
            result = "👥 **Пользователи:**\n"
            for i, u in enumerate(users[:30], 1):
                name = u['first_name'] or str(u['user_id'])
                result += f"{i}. {name} — {u['total_invites']}\n"
            result += f"\nВсего: {len(users)}"
            await message.reply(result, reply_markup=get_admin_keyboard())
        
        elif text == "📢 Рассылка":
            waiting_for_broadcast[user_id] = True
            await message.reply("📢 Отправь сообщение для рассылки", reply_markup=get_admin_keyboard())
        
        elif text == "📊 Статистика":
            files = db.fetch_one("SELECT COUNT(*) FROM files")[0]
            users = db.fetch_one("SELECT COUNT(*) FROM users")[0]
            invites = db.fetch_one("SELECT SUM(total_invites) FROM users")[0] or 0
            await message.reply(
                f"📊 **Статистика**\n\n📁 Читов: {files}\n👥 Пользователей: {users}\n🔗 Приглашений: {invites}",
                reply_markup=get_admin_keyboard()
            )
        
        elif text == "🧹 Очистка":
            db.execute("DELETE FROM users WHERE julianday('now') - julianday(last_active) > 30 AND user_id NOT IN (SELECT user_id FROM admins) AND user_id != ?", (ADMIN_ID,))
            await message.reply("✅ Очищено", reply_markup=get_admin_keyboard())
        
        elif text == "💾 Бэкап":
            if os.path.exists(DB_PATH):
                await message.reply_document(DB_PATH, caption=f"📦 Бэкап")
            else:
                await message.reply("Нет файла")

@app.on_message((filters.document | filters.video | filters.photo) & filters.private)
async def handle_file(client, message):
    user_id = message.from_user.id
    
    if not waiting_for_file.get(user_id, False):
        return
    
    if not is_admin(user_id):
        waiting_for_file[user_id] = False
        return
    
    status = await message.reply("⏳ Сохраняю...")
    
    try:
        sent = await message.copy(STORAGE_CHANNEL)
        file_hash = secrets.token_urlsafe(8)
        
        # Парсим подпись
        name = "Без названия"
        game = "Без игры"
        if message.caption and "|" in message.caption:
            parts = message.caption.split("|")
            name = parts[0].strip()
            game = parts[1].strip()
        elif message.caption:
            name = message.caption.strip()
        
        file_type = "doc" if message.document else "video" if message.video else "photo"
        
        db.execute(
            "INSERT INTO files (hash, remote_msg_id, type, name, game, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (file_hash, sent.id, file_type, name, game, user_id)
        )
        
        bot = await client.get_me()
        await status.edit_text(
            f"✅ **Добавлен!**\n\n"
            f"📄 {name}\n"
            f"🎮 {game}\n"
            f"🔗 `https://t.me/{bot.username}?start={file_hash}`"
        )
        
        waiting_for_file[user_id] = False
        
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        waiting_for_file[user_id] = False

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client, message):
    user_id = message.from_user.id
    if waiting_for_file.get(user_id):
        waiting_for_file[user_id] = False
        await message.reply("✅ Отменено")
    elif waiting_for_broadcast.get(user_id):
        waiting_for_broadcast[user_id] = False
        await message.reply("✅ Отменено")
    else:
        await message.reply("Нет активных операций")

# --- ЗАПУСК ---
if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    app.run()
