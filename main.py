import os
import sqlite3
import secrets
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Tuple
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import threading
import time

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
OWNER_ID = int(os.environ.get("OWNER_ID", 1471307057))
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/OfficialPlutonium")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "OfficialPlutonium")
STORAGE_CHANNEL = os.environ.get("STORAGE_CHANNEL", "IllyaTelegram")
DB_PATH = "files.db"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ID КАСТОМНЫХ ЭМОДЗИ (Premium) ---
class EmojiID:
    # Приветствие
    WAVE = "6041921818896372382"
    SMILE = "5289930378885214069"
    FOLDER = "5875008416132370818"
    
    # Профиль
    PROFILE = "6032693626394382504"
    ID_EMOJI = "5886505193180239900"
    NAME_EMOJI = "5879770735999717115"
    USERNAME_EMOJI = "5814247475141153332"
    FILES_EMOJI = "6039802767931871481"
    
    # Файл
    SEND_FILE = "6039573425268201570"
    SHOP = "5920332557466997677"
    
    # Подписка
    LOCK = "6037249452824072506"
    UNLOCK = "6039630677182254664"
    SUBSCRIBE = "5927118708873892465"
    CHECK = "5774022692642492953"
    
    # Стили кнопок
    DANGER = "5310169226856644648"
    SUCCESS = "5310076249404621168"
    PRIMARY = "5285430309720966085"
    DEFAULT = "5285032475490273112"
    
    # Premium
    CROWN = "5217822164362739968"

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
                file_id TEXT,
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
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (OWNER_ID, OWNER_ID))
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
        self.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (file_hash,))
        self.execute("UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?", (user_id,))

db = Database()

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С BOT API ---
def api_request(method: str, data: dict = None, files: dict = None) -> dict:
    """Отправка запроса к Bot API"""
    url = f"{API_URL}/{method}"
    
    try:
        if files:
            # Для отправки файлов используем multipart/form-data
            boundary = '--' + secrets.token_hex(16)
            body_parts = []
            
            for key, value in data.items():
                body_parts.append(f'--{boundary}')
                body_parts.append(f'Content-Disposition: form-data; name="{key}"')
                body_parts.append('')
                body_parts.append(str(value))
            
            for key, file_path in files.items():
                body_parts.append(f'--{boundary}')
                body_parts.append(f'Content-Disposition: form-data; name="{key}"; filename="{os.path.basename(file_path)}"')
                body_parts.append('Content-Type: application/octet-stream')
                body_parts.append('')
                with open(file_path, 'rb') as f:
                    body_parts.append(f.read())
            
            body_parts.append(f'--{boundary}--')
            
            body = b'\r\n'.join([part.encode() if isinstance(part, str) else part for part in body_parts])
            headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
            
            req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        else:
            # Обычный POST с JSON
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
            if not result.get('ok'):
                logger.error(f"API error: {result}")
            return result
            
    except Exception as e:
        logger.error(f"API request error: {e}")
        return {'ok': False, 'error': str(e)}

def send_message(chat_id: int, text: str, reply_markup: dict = None, parse_mode: str = "HTML") -> dict:
    """Отправить сообщение"""
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return api_request("sendMessage", data)

def send_document(chat_id: int, file_id: str, caption: str = None, reply_markup: dict = None) -> dict:
    """Отправить документ по file_id"""
    data = {
        "chat_id": chat_id,
        "document": file_id
    }
    if caption:
        data["caption"] = caption
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return api_request("sendDocument", data)

def copy_message(chat_id: int, from_chat_id: str, message_id: int, reply_markup: dict = None) -> dict:
    """Скопировать сообщение"""
    data = {
        "chat_id": chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return api_request("copyMessage", data)

def get_chat_member(chat_id: str, user_id: int) -> dict:
    """Получить информацию о участнике чата"""
    data = {
        "chat_id": chat_id,
        "user_id": user_id
    }
    return api_request("getChatMember", data)

def answer_callback_query(callback_query_id: str, text: str = None, show_alert: bool = False) -> dict:
    """Ответ на callback запрос"""
    data = {
        "callback_query_id": callback_query_id
    }
    if text:
        data["text"] = text
    if show_alert:
        data["show_alert"] = True
    return api_request("answerCallbackQuery", data)

def edit_message_text(chat_id: int, message_id: int, text: str, reply_markup: dict = None) -> dict:
    """Редактировать сообщение"""
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return api_request("editMessageText", data)

def get_file(file_id: str) -> dict:
    """Получить информацию о файле"""
    return api_request("getFile", {"file_id": file_id})

def download_file(file_path: str) -> bytes:
    """Скачать файл"""
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    with urllib.request.urlopen(url) as response:
        return response.read()

# --- ФУНКЦИИ ДЛЯ ФОРМАТИРОВАНИЯ ---
def emoji_html(emoji_id: str, char: str = "●") -> str:
    """Создает HTML тег с кастомным эмодзи"""
    return f'<tg-emoji emoji-id="{emoji_id}">{char}</tg-emoji>'

def create_inline_button(text: str, callback_data: str, emoji_id: str = None, style: str = None) -> dict:
    """Создает инлайн кнопку с кастомным эмодзи (как в примере)"""
    button = {
        "text": text,
        "callback_data": callback_data
    }
    
    if emoji_id:
        button["icon_custom_emoji_id"] = emoji_id
    
    if style:
        button["style"] = style
    
    return button

def create_reply_keyboard(buttons: list, resize: bool = True) -> dict:
    """Создает ReplyKeyboardMarkup"""
    return {
        "keyboard": buttons,
        "resize_keyboard": resize
    }

def create_inline_keyboard(buttons: list) -> dict:
    """Создает InlineKeyboardMarkup"""
    return {
        "inline_keyboard": buttons
    }

# --- КЛАВИАТУРЫ ---
def get_main_keyboard(is_premium: bool = False) -> dict:
    """Главная клавиатура с Reply-кнопками"""
    wave = emoji_html(EmojiID.WAVE, "👋") if is_premium else "👋"
    folder = emoji_html(EmojiID.FOLDER, "📁") if is_premium else "📁"
    
    return create_reply_keyboard([
        [[{"text": f"{folder} Игры"}]],
        [[{"text": f"{wave} Профиль"}], [{"text": "🔗 Рефералка"}]],
        [[{"text": "❓ Помощь"}]]
    ])

def get_admin_keyboard(is_premium: bool = False) -> dict:
    """Админ-панель"""
    return create_reply_keyboard([
        [[{"text": "📁 Добавить чит"}], [{"text": "📋 Список читов"}]],
        [[{"text": "👥 Пользователи"}], [{"text": "📢 Рассылка"}]],
        [[{"text": "📊 Статистика"}], [{"text": "🧹 Очистка"}]],
        [[{"text": "💾 Бэкап"}], [{"text": "🔙 Главное меню"}]]
    ])

def get_subscribe_keyboard(is_premium: bool = False) -> dict:
    """Инлайн кнопки для подписки"""
    subscribe_btn = {
        "text": "ПОДПИСАТЬСЯ",
        "url": CHANNEL_URL
    }
    check_btn = {
        "text": "ПРОВЕРИТЬ",
        "callback_data": "check_sub"
    }
    
    if is_premium:
        subscribe_btn["icon_custom_emoji_id"] = EmojiID.SUBSCRIBE
        check_btn["icon_custom_emoji_id"] = EmojiID.CHECK
    
    return create_inline_keyboard([
        [subscribe_btn],
        [check_btn]
    ])

def get_games_keyboard(games: list, is_premium: bool = False) -> dict:
    """Клавиатура с играми"""
    if not games:
        return None
    
    folder = emoji_html(EmojiID.FOLDER, "🎮") if is_premium else "🎮"
    buttons = []
    for game in games:
        buttons.append([[{"text": f"{folder} {game['game']}"}]])
    buttons.append([[{"text": "🔙 Главное меню"}]])
    return create_reply_keyboard(buttons)

def get_file_footer(is_premium: bool = False) -> str:
    """Футер для файлов"""
    send = emoji_html(EmojiID.SEND_FILE, "📤") if is_premium else "📤"
    shop = emoji_html(EmojiID.SHOP, "🏪") if is_premium else "🏪"
    return f"\n\n{send} **Ваш Файл**\n{shop} **Buy plutonium** - @PlutoniumllcBot"

def get_profile_text(user_data, user_id, is_premium: bool = False) -> str:
    """Текст профиля с кастомными эмодзи"""
    profile = emoji_html(EmojiID.PROFILE, "👤") if is_premium else "👤"
    id_emoji = emoji_html(EmojiID.ID_EMOJI, "🆔") if is_premium else "🆔"
    name_emoji = emoji_html(EmojiID.NAME_EMOJI, "📛") if is_premium else "📛"
    username_emoji = emoji_html(EmojiID.USERNAME_EMOJI, "🔖") if is_premium else "🔖"
    files_emoji = emoji_html(EmojiID.FILES_EMOJI, "📥") if is_premium else "📥"
    
    return (
        f"{profile} **Профиль**\n\n"
        f"{id_emoji} ID: `{user_id}`\n"
        f"{name_emoji} Имя: {user_data.get('first_name', '?')}\n"
        f"{username_emoji} Username: @{user_data.get('username', 'нет')}\n"
        f"{files_emoji} Файлов получено: {user_data.get('total_downloads', 0)}\n"
        f"👥 Приглашений: {user_data.get('total_invites', 0)}"
    )

def get_welcome_text(user_name: str, is_premium: bool = False) -> str:
    """Приветственный текст"""
    wave = emoji_html(EmojiID.WAVE, "👋") if is_premium else "👋"
    smile = emoji_html(EmojiID.SMILE, "🙂") if is_premium else "🙂"
    folder = emoji_html(EmojiID.FOLDER, "📁") if is_premium else "📁"
    
    return (
        f"{wave} **Привет, {user_name}!**\n\n"
        f"{smile} **Я храню файлы с канала** @OfficialPlutonium\n"
        f"{folder} **Используй кнопки ниже для навигации**"
    )

# --- ФУНКЦИИ ЛОГИКИ ---
def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    admin = db.fetch_one("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return admin is not None

def check_subscription_sync(user_id: int) -> bool:
    """Синхронная проверка подписки"""
    if not CHANNEL_ID:
        return True
    
    try:
        result = get_chat_member(CHANNEL_ID, user_id)
        if result.get('ok'):
            status = result['result']['status']
            return status in ['member', 'administrator', 'creator']
        return False
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return True

def save_user(user_id: int, username: str, first_name: str, last_name: str, is_premium: bool, inviter_id: int = None):
    """Сохранить пользователя"""
    db.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, is_premium, invited_by) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, first_name, last_name, 1 if is_premium else 0, inviter_id or 0)
    )
    
    if inviter_id and inviter_id != user_id:
        db.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter_id,))
        db.execute("INSERT INTO invites (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user_id))

def update_activity(user_id: int):
    db.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))

def get_user(user_id: int):
    return db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))

def get_all_games():
    return db.fetch_all("SELECT DISTINCT game FROM files WHERE game IS NOT NULL AND game != ''")

def get_files_by_game(game: str):
    return db.fetch_all("SELECT hash, file_id, name FROM files WHERE game = ?", (game,))

def get_file_by_name(name: str):
    return db.fetch_one("SELECT * FROM files WHERE name = ?", (name,))

def get_all_users():
    return db.fetch_all("SELECT user_id FROM users WHERE is_premium = 0")

def get_stats():
    files = db.fetch_one("SELECT COUNT(*) FROM files")[0]
    users = db.fetch_one("SELECT COUNT(*) FROM users")[0]
    invites = db.fetch_one("SELECT SUM(total_invites) FROM users")[0] or 0
    downloads = db.fetch_one("SELECT SUM(downloads) FROM files")[0] or 0
    premium = db.fetch_one("SELECT COUNT(*) FROM users WHERE is_premium = 1")[0]
    return {'files': files, 'users': users, 'invites': invites, 'downloads': downloads, 'premium': premium}

def cleanup_inactive():
    cursor = db.execute("""
        DELETE FROM users 
        WHERE julianday('now') - julianday(last_active) > 30 
        AND user_id NOT IN (SELECT user_id FROM admins)
        AND user_id != ?
    """, (OWNER_ID,))
    return cursor.rowcount

def get_all_files():
    return db.fetch_all("SELECT name, game, downloads FROM files ORDER BY game, name")

def add_file(file_hash: str, file_id: str, file_type: str, name: str, game: str, created_by: int):
    db.execute(
        "INSERT INTO files (hash, file_id, type, name, game, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        (file_hash, file_id, file_type, name, game, created_by)
    )

# --- ХРАНИЛИЩА ДЛЯ СОСТОЯНИЙ ---
waiting_for_file = {}
waiting_for_broadcast = {}

# --- ОБРАБОТЧИКИ ---
def process_message(chat_id: int, user_id: int, text: str, username: str = None, first_name: str = None, last_name: str = None, is_premium: bool = False, message_id: int = None):
    """Обработка текстовых сообщений"""
    
    # Рассылка
    if waiting_for_broadcast.get(user_id):
        if not is_admin(user_id):
            waiting_for_broadcast[user_id] = False
            return
        
        waiting_for_broadcast[user_id] = False
        users = get_all_users()
        
        if not users:
            send_message(chat_id, "Нет пользователей")
            return
        
        send_message(chat_id, f"🚀 Рассылка на {len(users)}...")
        sent = 0
        failed = 0
        
        for user in users:
            try:
                send_message(user['user_id'], text)
                sent += 1
            except:
                failed += 1
        
        send_message(chat_id, f"✅ Готово!\n✅ {sent}\n❌ {failed}")
        return
    
    # Проверка подписки
    if not check_subscription_sync(user_id):
        send_message(
            chat_id,
            f"🔒 **Привет, {first_name}!**\n\n🔓 **Подпишись на канал для доступа к читам.**",
            get_subscribe_keyboard(is_premium)
        )
        return
    
    update_activity(user_id)
    
    # --- КНОПКИ ---
    if text == "🔙 Главное меню":
        keyboard = get_admin_keyboard(is_premium) if is_admin(user_id) else get_main_keyboard(is_premium)
        send_message(chat_id, "Главное меню:", keyboard)
    
    elif text == "🔙 Назад к играм":
        games = get_all_games()
        keyboard = get_games_keyboard(games, is_premium)
        if keyboard:
            send_message(chat_id, "🎮 Выбери игру:", keyboard)
        else:
            send_message(chat_id, "📭 Нет игр", get_main_keyboard(is_premium))
    
    elif text == "👤 Профиль" or (text.startswith("👋") and "Профиль" in text):
        user_data = get_user(user_id)
        profile_text = get_profile_text(user_data or {}, user_id, is_premium)
        send_message(chat_id, profile_text, get_main_keyboard(is_premium))
    
    elif text == "🔗 Рефералка":
        ref_link = f"https://t.me/PlutoniumCheatsBot?start=ref_{user_id}"
        send_message(chat_id, f"🔗 **Рефералка**\n\n`{ref_link}`", get_main_keyboard(is_premium))
    
    elif text == "❓ Помощь":
        help_text = (
            "📋 **Как пользоваться ботом:**\n\n"
            "1️⃣ Нажми «Игры»\n"
            "2️⃣ Выбери игру\n"
            "3️⃣ Нажми на название чита\n"
            "4️⃣ Файл автоматически отправится\n\n"
            "🔗 **Рефералка:** приглашай друзей!"
        )
        send_message(chat_id, help_text, get_main_keyboard(is_premium))
    
    elif text == "🎮 Игры" or (text.startswith("📁") and "Игры" in text):
        games = get_all_games()
        keyboard = get_games_keyboard(games, is_premium)
        if keyboard:
            send_message(chat_id, "🎮 **Доступные игры:**", keyboard)
        else:
            send_message(chat_id, "📭 Пока нет доступных читов.", get_main_keyboard(is_premium))
    
    elif text.startswith("🎮") or (text.startswith("📁") and len(text) > 2):
        game = text.split(" ", 1)[-1] if " " in text else text[2:]
        files = get_files_by_game(game)
        if files:
            buttons = []
            for f in files:
                buttons.append([[{"text": f"📄 {f['name'][:30]}", "callback_data": f"file_{f['hash']}"}]])
            buttons.append([[{"text": "🔙 Назад к играм"}]])
            send_message(chat_id, f"🎮 **{game}**\n\nВыбери чит:", create_reply_keyboard(buttons))
        else:
            send_message(chat_id, f"❌ Для игры {game} пока нет читов.", get_games_keyboard(get_all_games(), is_premium))
    
    # --- АДМИН КНОПКИ ---
    elif is_admin(user_id):
        if text == "📁 Добавить чит":
            waiting_for_file[user_id] = True
            send_message(
                chat_id,
                "📤 **Добавление чита**\n\n"
                "1. Отправь файл\n"
                "2. В подписи: `Название | Игра`\n\n"
                "Пример: `Aimbot | CS2`\n\n"
                "/cancel - отмена",
                get_admin_keyboard(is_premium)
            )
        
        elif text == "📋 Список читов":
            files = get_all_files()
            if not files:
                send_message(chat_id, "Пусто", get_admin_keyboard(is_premium))
                return
            result = "📋 **Читы:**\n"
            for f in files:
                result += f"\n🎮 {f['game']}\n  • {f['name']} (⬇️ {f['downloads']})"
            send_message(chat_id, result[:4000], get_admin_keyboard(is_premium))
        
        elif text == "👥 Пользователи":
            users = db.fetch_all("SELECT user_id, first_name, total_invites, total_downloads, is_premium FROM users ORDER BY total_downloads DESC")
            result = "👥 **Пользователи:**\n\n"
            for i, u in enumerate(users[:30], 1):
                name = u['first_name'] or str(u['user_id'])
                premium = "👑" if u['is_premium'] else ""
                result += f"{i}. {name} {premium} — пригл: {u['total_invites']} | ⬇️ {u['total_downloads']}\n"
            result += f"\n📊 Всего: {len(users)}"
            send_message(chat_id, result, get_admin_keyboard(is_premium))
        
        elif text == "📢 Рассылка":
            waiting_for_broadcast[user_id] = True
            send_message(chat_id, "📢 Отправь сообщение для рассылки", get_admin_keyboard(is_premium))
        
        elif text == "📊 Статистика":
            stats = get_stats()
            send_message(
                chat_id,
                f"📊 **Статистика**\n\n"
                f"📁 Читов: {stats['files']}\n"
                f"👥 Пользователей: {stats['users']}\n"
                f"👑 Премиум: {stats['premium']}\n"
                f"⬇️ Скачиваний: {stats['downloads']}\n"
                f"🔗 Приглашений: {stats['invites']}",
                get_admin_keyboard(is_premium)
            )
        
        elif text == "🧹 Очистка":
            deleted = cleanup_inactive()
            send_message(chat_id, f"✅ Удалено неактивных: {deleted}", get_admin_keyboard(is_premium))
        
        elif text == "💾 Бэкап":
            if os.path.exists(DB_PATH):
                # Отправляем файл
                with open(DB_PATH, 'rb') as f:
                    # Для отправки файла используем multipart
                    url = f"{API_URL}/sendDocument"
                    boundary = '--' + secrets.token_hex(16)
                    body_parts = []
                    
                    body_parts.append(f'--{boundary}')
                    body_parts.append(f'Content-Disposition: form-data; name="chat_id"')
                    body_parts.append('')
                    body_parts.append(str(chat_id))
                    
                    body_parts.append(f'--{boundary}')
                    body_parts.append(f'Content-Disposition: form-data; name="document"; filename="files.db"')
                    body_parts.append('Content-Type: application/octet-stream')
                    body_parts.append('')
                    body_parts.append(f.read())
                    
                    body_parts.append(f'--{boundary}--')
                    
                    body = b'\r\n'.join([part.encode() if isinstance(part, str) else part for part in body_parts])
                    headers = {'Content-Type': f'multipart/form-data; boundary={boundary}'}
                    
                    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
                    urllib.request.urlopen(req, timeout=30)
            else:
                send_message(chat_id, "Нет файла")

def process_callback(callback_id: str, chat_id: int, message_id: int, data: str, user_id: int, is_premium: bool = False):
    """Обработка callback запросов"""
    
    if data == "check_sub":
        subscribed = check_subscription_sync(user_id)
        
        if subscribed:
            user_data = get_user(user_id)
            user_name = user_data.get('first_name', 'Пользователь') if user_data else 'Пользователь'
            welcome_text = get_welcome_text(user_name, is_premium)
            keyboard = get_admin_keyboard(is_premium) if is_admin(user_id) else get_main_keyboard(is_premium)
            edit_message_text(chat_id, message_id, welcome_text, keyboard)
            answer_callback_query(callback_id, "✅ Подписка подтверждена!")
        else:
            answer_callback_query(callback_id, "❌ Вы еще не подписались!", True)
    
    elif data.startswith("file_"):
        file_hash = data.split("_")[1]
        file_data = db.fetch_one("SELECT file_id, name FROM files WHERE hash = ?", (file_hash,))
        
        if file_data:
            db.increment_downloads(file_hash, user_id)
            footer = get_file_footer(is_premium)
            send_document(chat_id, file_data['file_id'], f"✅ {file_data['name']} отправлен!{footer}")
            answer_callback_query(callback_id, f"✅ {file_data['name']} отправлен!")
        else:
            answer_callback_query(callback_id, "❌ Файл не найден", True)

def process_document(chat_id: int, user_id: int, file_id: str, file_name: str, caption: str = None):
    """Обработка документов (загрузка читов админом)"""
    
    if not waiting_for_file.get(user_id, False):
        return
    
    if not is_admin(user_id):
        waiting_for_file[user_id] = False
        return
    
    waiting_for_file[user_id] = False
    
    # Парсим подпись
    name = file_name
    game = "Без игры"
    if caption and "|" in caption:
        parts = caption.split("|")
        name = parts[0].strip()
        game = parts[1].strip()
    elif caption:
        name = caption.strip()
    
    file_hash = secrets.token_urlsafe(8)
    add_file(file_hash, file_id, "doc", name, game, user_id)
    
    send_message(
        chat_id,
        f"✅ **Чит добавлен!**\n\n📄 {name}\n🎮 {game}\n🔗 `https://t.me/PlutoniumCheatsBot?start={file_hash}`",
        get_admin_keyboard(True)
    )

# --- WEBHOOK СЕРВЕР ---
class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/webhook':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                update = json.loads(post_data.decode())
                logger.info(f"Update: {update}")
                
                # Обработка callback_query
                if 'callback_query' in update:
                    callback = update['callback_query']
                    callback_id = callback['id']
                    chat_id = callback['message']['chat']['id']
                    message_id = callback['message']['message_id']
                    data = callback['data']
                    user = callback['from']
                    user_id = user['id']
                    is_premium = user.get('is_premium', False)
                    
                    # Запускаем в отдельном потоке
                    threading.Thread(
                        target=process_callback,
                        args=(callback_id, chat_id, message_id, data, user_id, is_premium)
                    ).start()
                
                # Обработка сообщений
                elif 'message' in update:
                    msg = update['message']
                    chat_id = msg['chat']['id']
                    user = msg['from']
                    user_id = user['id']
                    username = user.get('username', '')
                    first_name = user.get('first_name', '')
                    last_name = user.get('last_name', '')
                    is_premium = user.get('is_premium', False)
                    
                    # Сохраняем пользователя при первом сообщении
                    if not get_user(user_id):
                        save_user(user_id, username, first_name, last_name, is_premium)
                    
                    # Команда /start
                    if 'text' in msg and msg['text'].startswith('/start'):
                        args = msg['text'].replace('/start', '').strip()
                        inviter_id = None
                        if args.startswith('ref_'):
                            try:
                                inviter_id = int(args.split('_')[1])
                                if inviter_id != user_id:
                                    save_user(user_id, username, first_name, last_name, is_premium, inviter_id)
                            except:
                                pass
                        
                        subscribed = check_subscription_sync(user_id)
                        user_name = first_name or str(user_id)
                        
                        if not subscribed:
                            send_message(
                                chat_id,
                                f"🔒 **Привет, {user_name}!**\n\n🔓 **Подпишись на канал для доступа к читам.**",
                                get_subscribe_keyboard(is_premium)
                            )
                        else:
                            welcome_text = get_welcome_text(user_name, is_premium)
                            user_data = get_user(user_id)
                            invites = user_data.get('total_invites', 0) if user_data else 0
                            welcome_text += f"\n\n👥 Приглашений: {invites}"
                            keyboard = get_admin_keyboard(is_premium) if is_admin(user_id) else get_main_keyboard(is_premium)
                            send_message(chat_id, welcome_text, keyboard)
                    
                    # Текстовое сообщение
                    elif 'text' in msg:
                        threading.Thread(
                            target=process_message,
                            args=(chat_id, user_id, msg['text'], username, first_name, last_name, is_premium, msg['message_id'])
                        ).start()
                    
                    # Документ
                    elif 'document' in msg:
                        file_id = msg['document']['file_id']
                        file_name = msg['document'].get('file_name', 'file')
                        caption = msg.get('caption')
                        threading.Thread(
                            target=process_document,
                            args=(chat_id, user_id, file_id, file_name, caption)
                        ).start()
                
            except Exception as e:
                logger.error(f"Webhook error: {e}")
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running!')

def set_webhook():
    """Установка вебхука"""
    webhook_url = os.environ.get("RAILWAY_PUBLIC_URL", "")
    if not webhook_url:
        logger.warning("RAILWAY_PUBLIC_URL not set, using localhost")
        return
    
    url = f"{webhook_url}/webhook"
    result = api_request("setWebhook", {"url": url})
    if result.get('ok'):
        logger.info(f"✅ Webhook set: {url}")
    else:
        logger.error(f"❌ Webhook error: {result}")

# --- ЗАПУСК ---
if __name__ == "__main__":
    logger.info("🚀 Запуск Plutonium Bot (Bot API)")
    logger.info(f"👑 Владелец: {OWNER_ID}")
    logger.info(f"📢 Канал: {CHANNEL_ID}")
    
    # Устанавливаем вебхук
    set_webhook()
    
    # Запускаем сервер
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    logger.info(f"🌐 Server running on port {port}")
    server.serve_forever()
 
