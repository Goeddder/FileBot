import os
import sqlite3
import secrets
import asyncio
import shutil
import logging
from datetime import datetime
from typing import Optional, Tuple

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    CallbackQuery, Message
)
from pyrogram.errors import UserNotParticipant, FloodWait, ChatAdminRequired
from pyrogram.enums import ParseMode

# --- НАСТРОЙКИ ---
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

# --- ЭМОДЗИ ID (Premium) ---
class Emoji:
    # Приветствие
    WAVE = "6041921818896372382"      # 👋
    SMILE = "5289930378885214069"     # 🙂
    FOLDER = "5875008416132370818"    # 📁
    
    # Профиль
    PROFILE = "6032693626394382504"   # 👤
    ID_EMOJI = "5886505193180239900"  # 🆔
    NAME_EMOJI = "5879770735999717115" # 📛
    USERNAME_EMOJI = "5814247475141153332" # 🔖
    FILES_EMOJI = "6039802767931871481" # 📥
    
    # Файл
    SEND_FILE = "6039573425268201570"  # 📤
    SHOP = "5920332557466997677"       # 🏪
    
    # Подписка
    LOCK = "6037249452824072506"       # 🔒
    UNLOCK = "6039630677182254664"     # 🔓
    
    # Кнопки
    SUBSCRIBE = "5927118708873892465"  # 📢
    CHECK = "5774022692642492953"      # 🔄
    
    # Premium
    CROWN = "5217822164362739968"      # 👑
    STAR = "5285430309720966085"       # ⭐

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
                downloads INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_premium INTEGER DEFAULT 0,
                invited_by INTEGER DEFAULT 0,
                total_invites INTEGER DEFAULT 0,
                total_downloads INTEGER DEFAULT 0,
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
    
    def increment_downloads(self, file_hash: str, user_id: int):
        """Увеличить счетчик скачиваний"""
        self.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (file_hash,))
        self.execute("UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?", (user_id,))

db = Database()

# --- КЛАВИАТУРЫ (Premium с кастомными эмодзи) ---
def get_main_keyboard(is_premium: bool = False):
    """Главная клавиатура с премиум-эмодзи"""
    wave_emoji = f"<tg-emoji emoji-id=\"{Emoji.WAVE}\">👋</tg-emoji>" if is_premium else "👋"
    folder_emoji = f"<tg-emoji emoji-id=\"{Emoji.FOLDER}\">📁</tg-emoji>" if is_premium else "📁"
    
    return ReplyKeyboardMarkup([
        [KeyboardButton(f"{folder_emoji} Игры")],
        [KeyboardButton(f"{wave_emoji} Профиль"), KeyboardButton("🔗 Рефералка")],
        [KeyboardButton("❓ Помощь")]
    ], resize_keyboard=True)

def get_admin_keyboard(is_premium: bool = False):
    """Админ-панель с премиум-эмодзи"""
    return ReplyKeyboardMarkup([
        [KeyboardButton("📁 Добавить чит"), KeyboardButton("📋 Список читов")],
        [KeyboardButton("👥 Пользователи"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("🧹 Очистка")],
        [KeyboardButton("💾 Бэкап"), KeyboardButton("🔙 Главное меню")]
    ], resize_keyboard=True)

def get_games_keyboard(games: list, is_premium: bool = False):
    """Клавиатура с играми"""
    if not games:
        return None
    
    folder_emoji = f"<tg-emoji emoji-id=\"{Emoji.FOLDER}\">📁</tg-emoji>" if is_premium else "🎮"
    buttons = []
    for game in games:
        buttons.append([KeyboardButton(f"{folder_emoji} {game['game']}")])
    buttons.append([KeyboardButton("🔙 Главное меню")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_cheats_keyboard(cheats: list, game: str, is_premium: bool = False):
    """Клавиатура с читами"""
    if not cheats:
        return None
    
    send_emoji = f"<tg-emoji emoji-id=\"{Emoji.SEND_FILE}\">📤</tg-emoji>" if is_premium else "📄"
    buttons = []
    for cheat in cheats:
        buttons.append([KeyboardButton(f"{send_emoji} {cheat['name'][:30]}")])
    buttons.append([KeyboardButton("🔙 Назад к играм")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_subscribe_keyboard(is_premium: bool = False):
    """Кнопка подписки с премиум-эмодзи"""
    subscribe_emoji = f"<tg-emoji emoji-id=\"{Emoji.SUBSCRIBE}\">📢</tg-emoji>" if is_premium else "📢"
    check_emoji = f"<tg-emoji emoji-id=\"{Emoji.CHECK}\">🔄</tg-emoji>" if is_premium else "🔄"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{subscribe_emoji} ПОДПИСАТЬСЯ", url=CHANNEL_URL)],
        [InlineKeyboardButton(f"{check_emoji} ПРОВЕРИТЬ", callback_data="check_sub")]
    ])

def get_file_footer(is_premium: bool = False):
    """Футер для файлов"""
    send_emoji = f"<tg-emoji emoji-id=\"{Emoji.SEND_FILE}\">📤</tg-emoji>" if is_premium else "📤"
    shop_emoji = f"<tg-emoji emoji-id=\"{Emoji.SHOP}\">🏪</tg-emoji>" if is_premium else "🏪"
    
    return f"\n\n{send_emoji} **Ваш Файл**\n{shop_emoji} **Buy plutonium** - @PlutoniumllcBot"

# --- ФУНКЦИЯ ПРОВЕРКИ ПОДПИСКИ ---
async def check_subscription(client, user_id):
    if not CHANNEL_ID:
        return True
    try:
        chat_id = CHANNEL_ID.replace("@", "")
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in ["member", "administrator", "creator"]
    except UserNotParticipant:
        return False
    except ChatAdminRequired:
        logger.error(f"Бот не админ канала {CHANNEL_ID}")
        return True
    except Exception as e:
        logger.error(f"Ошибка подписки: {e}")
        return True

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    admin = db.fetch_one("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return admin is not None

def format_user_name(user):
    """Форматирование имени пользователя с премиум-статусом"""
    name = user.first_name or str(user.id)
    if user.last_name:
        name += f" {user.last_name}"
    
    # Добавляем премиум-эмодзи если есть
    if user.is_premium:
        crown_emoji = f"<tg-emoji emoji-id=\"{Emoji.CROWN}\">👑</tg-emoji>"
        name = f"{name} {crown_emoji}"
    
    return name

# --- КЛИЕНТ ---
app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

waiting_for_file = {}
waiting_for_broadcast = {}

# --- ОБРАБОТЧИКИ ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user = message.from_user
    inviter_id = None
    is_premium = getattr(user, 'is_premium', False)
    
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
        "INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, is_premium, invited_by) VALUES (?, ?, ?, ?, ?, ?)",
        (user.id, user.username, user.first_name, user.last_name, 1 if is_premium else 0, inviter_id or 0)
    )
    
    if inviter_id and inviter_id != user.id:
        db.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter_id,))
        db.execute("INSERT INTO invites (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user.id))
    
    # Проверка подписки
    subscribed = await check_subscription(client, user.id)
    
    # Форматируем имя с премиумом
    user_name = format_user_name(user)
    
    if not subscribed:
        lock_emoji = f"<tg-emoji emoji-id=\"{Emoji.LOCK}\">🔒</tg-emoji>" if is_premium else "🔒"
        unlock_emoji = f"<tg-emoji emoji-id=\"{Emoji.UNLOCK}\">🔓</tg-emoji>" if is_premium else "🔓"
        
        await message.reply(
            f"{lock_emoji} **Привет, {user_name}!**\n\n"
            f"{unlock_emoji} **Подпишись на канал для доступа к читам.**",
            reply_markup=get_subscribe_keyboard(is_premium),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Приветствие для подписанных
    wave_emoji = f"<tg-emoji emoji-id=\"{Emoji.WAVE}\">👋</tg-emoji>" if is_premium else "👋"
    smile_emoji = f"<tg-emoji emoji-id=\"{Emoji.SMILE}\">🙂</tg-emoji>" if is_premium else "🙂"
    folder_emoji = f"<tg-emoji emoji-id=\"{Emoji.FOLDER}\">📁</tg-emoji>" if is_premium else "📁"
    
    user_data = db.fetch_one("SELECT total_invites, total_downloads FROM users WHERE user_id = ?", (user.id,))
    invites = user_data['total_invites'] if user_data else 0
    
    await message.reply(
        f"{wave_emoji} **Привет, {user_name}!**\n\n"
        f"{smile_emoji} **Я храню файлы с канала** @OfficialPlutonium\n"
        f"{folder_emoji} **Используй кнопки ниже для навигации**\n\n"
        f"👥 Приглашений: {invites}",
        reply_markup=get_main_keyboard(is_premium) if not is_admin(user.id) else get_admin_keyboard(is_premium),
        parse_mode=ParseMode.HTML
    )

@app.on_callback_query()
async def handle_callback(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    is_premium = getattr(callback.from_user, 'is_premium', False)
    
    if data == "check_sub":
        subscribed = await check_subscription(client, user_id)
        
        if subscribed:
            user_name = format_user_name(callback.from_user)
            wave_emoji = f"<tg-emoji emoji-id=\"{Emoji.WAVE}\">👋</tg-emoji>" if is_premium else "👋"
            smile_emoji = f"<tg-emoji emoji-id=\"{Emoji.SMILE}\">🙂</tg-emoji>" if is_premium else "🙂"
            folder_emoji = f"<tg-emoji emoji-id=\"{Emoji.FOLDER}\">📁</tg-emoji>" if is_premium else "📁"
            
            keyboard = get_admin_keyboard(is_premium) if is_admin(user_id) else get_main_keyboard(is_premium)
            
            await callback.message.edit_text(
                f"{wave_emoji} **Привет, {user_name}!**\n\n"
                f"{smile_emoji} **Я храню файлы с канала** @OfficialPlutonium\n"
                f"{folder_emoji} **Используй кнопки ниже для навигации**",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
        else:
            await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)

@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.from_user.id
    text = message.text
    is_premium = getattr(message.from_user, 'is_premium', False)
    
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
    subscribed = await check_subscription(client, user_id)
    if not subscribed:
        lock_emoji = f"<tg-emoji emoji-id=\"{Emoji.LOCK}\">🔒</tg-emoji>" if is_premium else "🔒"
        unlock_emoji = f"<tg-emoji emoji-id=\"{Emoji.UNLOCK}\">🔓</tg-emoji>" if is_premium else "🔓"
        
        await message.reply(
            f"{lock_emoji} **Доступ ограничен!**\n\n"
            f"{unlock_emoji} Подпишись на канал: {CHANNEL_URL}",
            reply_markup=get_subscribe_keyboard(is_premium),
            parse_mode=ParseMode.HTML
        )
        return
    
    db.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
    
    # --- КНОПКИ ---
    if text == "🔙 Главное меню":
        keyboard = get_admin_keyboard(is_premium) if is_admin(user_id) else get_main_keyboard(is_premium)
        await message.reply("Главное меню:", reply_markup=keyboard)
    
    elif text == "🔙 Назад к играм":
        games = db.fetch_all("SELECT DISTINCT game FROM files WHERE game IS NOT NULL AND game != ''")
        keyboard = get_games_keyboard(games, is_premium)
        if keyboard:
            await message.reply("🎮 Выбери игру:", reply_markup=keyboard)
        else:
            await message.reply("📭 Нет игр", reply_markup=get_main_keyboard(is_premium))
    
    elif text == "👤 Профиль" or text.startswith("👋") and "Профиль" in text:
        user_data = db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        invites = user_data['total_invites'] if user_data else 0
        downloads = user_data['total_downloads'] if user_data else 0
        created = user_data['created_at'] if user_data else "?"
        
        profile_emoji = f"<tg-emoji emoji-id=\"{Emoji.PROFILE}\">👤</tg-emoji>" if is_premium else "👤"
        id_emoji = f"<tg-emoji emoji-id=\"{Emoji.ID_EMOJI}\">🆔</tg-emoji>" if is_premium else "🆔"
        name_emoji = f"<tg-emoji emoji-id=\"{Emoji.NAME_EMOJI}\">📛</tg-emoji>" if is_premium else "📛"
        username_emoji = f"<tg-emoji emoji-id=\"{Emoji.USERNAME_EMOJI}\">🔖</tg-emoji>" if is_premium else "🔖"
        files_emoji = f"<tg-emoji emoji-id=\"{Emoji.FILES_EMOJI}\">📥</tg-emoji>" if is_premium else "📥"
        
        user_name = format_user_name(message.from_user)
        username = f"@{message.from_user.username}" if message.from_user.username else "Нет"
        
        await message.reply(
            f"{profile_emoji} **Профиль**\n\n"
            f"{id_emoji} ID: `{user_id}`\n"
            f"{name_emoji} Имя: {user_name}\n"
            f"{username_emoji} Username: {username}\n"
            f"{files_emoji} Файлов получено: {downloads}\n"
            f"👥 Приглашений: {invites}\n"
            f"📅 Регистрация: {created}",
            reply_markup=get_main_keyboard(is_premium),
            parse_mode=ParseMode.HTML
        )
    
    elif text == "🔗 Рефералка":
        bot = await client.get_me()
        await message.reply(
            f"🔗 **Твоя реферальная ссылка:**\n\n"
            f"`https://t.me/{bot.username}?start=ref_{user_id}`\n\n"
            f"📢 Отправь ссылку друзьям!",
            reply_markup=get_main_keyboard(is_premium)
        )
    
    elif text == "❓ Помощь":
        await message.reply(
            "📋 **Как пользоваться ботом:**\n\n"
            "1️⃣ Нажми «Игры»\n"
            "2️⃣ Выбери игру\n"
            "3️⃣ Нажми на название чита\n"
            "4️⃣ Файл автоматически отправится\n\n"
            "🔗 **Рефералка:** приглашай друзей!\n\n"
            "👑 **Premium:** особые эмодзи и стили",
            reply_markup=get_main_keyboard(is_premium)
        )
    
    elif text == "🎮 Игры" or text.startswith("📁") and "Игры" in text:
        games = db.fetch_all("SELECT DISTINCT game FROM files WHERE game IS NOT NULL AND game != ''")
        keyboard = get_games_keyboard(games, is_premium)
        if keyboard:
            await message.reply("🎮 **Доступные игры:**", reply_markup=keyboard)
        else:
            await message.reply("📭 Пока нет доступных читов.", reply_markup=get_main_keyboard(is_premium))
    
    elif text.startswith("🎮") or (text.startswith("📁") and len(text) > 2):
        # Убираем эмодзи
        game = text.split(" ", 1)[-1] if " " in text else text[2:]
        cheats = db.fetch_all("SELECT name FROM files WHERE game = ?", (game,))
        keyboard = get_cheats_keyboard(cheats, game, is_premium)
        if keyboard:
            await message.reply(f"🎮 **{game}**\n\nВыбери чит:", reply_markup=keyboard)
        else:
            await message.reply(f"❌ Для игры {game} пока нет читов.", reply_markup=get_games_keyboard(db.fetch_all("SELECT DISTINCT game FROM files"), is_premium))
    
    elif text.startswith("📄") or (text.startswith("📤") and len(text) > 2):
        cheat_name = text.split(" ", 1)[-1] if " " in text else text[2:]
        file_data = db.fetch_one("SELECT remote_msg_id, name FROM files WHERE name = ?", (cheat_name,))
        if file_data:
            try:
                await client.copy_message(user_id, STORAGE_CHANNEL, file_data['remote_msg_id'])
                db.increment_downloads(file_data['hash'] if 'hash' in file_data else None, user_id)
                
                # Футер с эмодзи
                footer = get_file_footer(is_premium)
                await message.reply(f"✅ {file_data['name']} отправлен!{footer}", reply_markup=get_games_keyboard(db.fetch_all("SELECT DISTINCT game FROM files"), is_premium), parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Send error: {e}")
                await message.reply(f"❌ Ошибка загрузки.", reply_markup=get_games_keyboard(db.fetch_all("SELECT DISTINCT game FROM files"), is_premium))
        else:
            await message.reply(f"❌ Чит не найден.", reply_markup=get_games_keyboard(db.fetch_all("SELECT DISTINCT game FROM files"), is_premium))
    
    # --- АДМИН КНОПКИ (без изменений) ---
    elif is_admin(user_id):
        if text == "📁 Добавить чит":
            waiting_for_file[user_id] = True
            await message.reply(
                "📤 **Добавление чита**\n\n"
                "1. Отправь файл\n"
                "2. В подписи: `Название | Игра`\n\n"
                "Пример: `Aimbot | CS2`\n\n"
                "/cancel - отмена",
                reply_markup=get_admin_keyboard(is_premium)
            )
        
        elif text == "📋 Список читов":
            files = db.fetch_all("SELECT name, game, downloads FROM files ORDER BY game, name")
            if not files:
                await message.reply("Пусто", reply_markup=get_admin_keyboard(is_premium))
                return
            result = "📋 **Читы:**\n"
            for f in files:
                result += f"\n🎮 {f['game']}\n  • {f['name']} (⬇️ {f['downloads']})"
            await message.reply(result[:4000], reply_markup=get_admin_keyboard(is_premium))
        
        elif text == "👥 Пользователи":
            users = db.fetch_all("SELECT user_id, first_name, total_invites, total_downloads, is_premium FROM users ORDER BY total_downloads DESC")
            result = "👥 **Пользователи:**\n\n"
            for i, u in enumerate(users[:30], 1):
                name = u['first_name'] or str(u['user_id'])
                premium = "👑" if u['is_premium'] else ""
                result += f"{i}. {name} {premium} — пригл: {u['total_invites']} | ⬇️ {u['total_downloads']}\n"
            result += f"\n📊 Всего: {len(users)}"
            await message.reply(result, reply_markup=get_admin_keyboard(is_premium))
        
        elif text == "📢 Рассылка":
            waiting_for_broadcast[user_id] = True
            await message.reply("📢 Отправь сообщение для рассылки", reply_markup=get_admin_keyboard(is_premium))
        
        elif text == "📊 Статистика":
            files = db.fetch_one("SELECT COUNT(*) FROM files")[0]
            users = db.fetch_one("SELECT COUNT(*) FROM users")[0]
            invites = db.fetch_one("SELECT SUM(total_invites) FROM users")[0] or 0
            downloads = db.fetch_one("SELECT SUM(downloads) FROM files")[0] or 0
            premium = db.fetch_one("SELECT COUNT(*) FROM users WHERE is_premium = 1")[0]
            await message.reply(
                f"📊 **Статистика**\n\n"
                f"📁 Читов: {files}\n"
                f"👥 Пользователей: {users}\n"
                f"👑 Премиум: {premium}\n"
                f"⬇️ Скачиваний: {downloads}\n"
                f"🔗 Приглашений: {invites}",
                reply_markup=get_admin_keyboard(is_premium)
            )
        
        elif text == "🧹 Очистка":
            db.execute("DELETE FROM users WHERE julianday('now') - julianday(last_active) > 30 AND user_id NOT IN (SELECT user_id FROM admins) AND user_id != ?", (ADMIN_ID,))
            await message.reply("✅ Очищено", reply_markup=get_admin_keyboard(is_premium))
        
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
    logger.info("🚀 Запуск Plutonium Bot (Premium Ready)...")
    logger.info(f"👑 Владелец: {ADMIN_ID}")
    logger.info(f"📢 Канал: {CHANNEL_ID}")
    app.run()
