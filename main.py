import os
import sqlite3
import secrets
import json
import logging
import urllib.request
import time
import threading
import tempfile

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8071432823:AAHh27N0UVMpt3grjhL0XX_XypAncrF8Mi8"
OWNER_ID = 1471307057
PHOTO_URL = "https://files.catbox.moe/jdtlab.jpg"
DB_PATH = "plutonium_full.db"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ID каналов
CHANNEL_ID = -1003607014773
STORAGE_CHANNEL_ID = -1003677537552

# Turso настройки
TURSO_URL = os.environ.get("TURSO_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
USE_TURSO = bool(TURSO_URL and TURSO_AUTH_TOKEN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ ---
if USE_TURSO:
    try:
        import libsql_experimental as sqlite3
        conn = sqlite3.connect(TURSO_URL)
        conn.execute("PRAGMA journal_mode=WAL")
        logger.info("✅ Подключено к Turso")
    except ImportError:
        logger.error("❌ libsql_experimental не установлен")
        USE_TURSO = False
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
else:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    logger.info("✅ Подключено к локальной SQLite")

conn.row_factory = sqlite3.Row

def init_db():
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS files (
        hash TEXT PRIMARY KEY, 
        file_id INTEGER, 
        name TEXT, 
        description TEXT, 
        game TEXT, 
        ts INTEGER, 
        created_by INTEGER, 
        downloads INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, 
        username TEXT, 
        first_name TEXT, 
        downloads INTEGER DEFAULT 0, 
        banned INTEGER DEFAULT 0, 
        last_active INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY, 
        perms TEXT, 
        added_by INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS op_settings (
        id INTEGER PRIMARY KEY, 
        channel_id INTEGER, 
        target INTEGER DEFAULT 0, 
        current INTEGER DEFAULT 0, 
        active INTEGER DEFAULT 0, 
        link TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ads (
        msg_id INTEGER PRIMARY KEY, 
        chat_id INTEGER, 
        expire INTEGER, 
        message_data TEXT
    )""")
    c.execute("INSERT OR IGNORE INTO admins (user_id, perms, added_by) VALUES (?, ?, ?)", 
              (OWNER_ID, '["all"]', OWNER_ID))
    conn.commit()
    logger.info("✅ База данных готова")

init_db()

# --- ФУНКЦИИ API С ПОВТОРАМИ ---
def api(method, data=None, retry=3):
    url = f"{API_URL}/{method}"
    for attempt in range(retry):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode() if data else None,
                headers={'Content-Type': 'application/json'} if data else {},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            logger.error(f"API error ({method}): {e}")
            if attempt == retry - 1:
                return {'ok': False}
            time.sleep(1)
    return {'ok': False}

def has_perm(uid, perm):
    if uid == OWNER_ID:
        return True
    row = conn.execute("SELECT perms FROM admins WHERE user_id = ?", (uid,)).fetchone()
    if not row:
        return False
    p = json.loads(row['perms'])
    return "all" in p or perm in p

def is_admin(uid):
    if uid == OWNER_ID:
        return True
    return conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (uid,)).fetchone() is not None

# --- ТАЙМЕР УДАЛЕНИЯ РЕКЛАМЫ ---
def ad_cleaner():
    while True:
        try:
            now = int(time.time())
            expired = conn.execute("SELECT * FROM ads WHERE expire < ?", (now,)).fetchall()
            for ad in expired:
                api("deleteMessage", {"chat_id": ad['chat_id'], "message_id": ad['msg_id']})
                conn.execute("DELETE FROM ads WHERE msg_id = ?", (ad['msg_id'],))
            conn.commit()
        except Exception as e:
            logger.error(f"Ad cleaner error: {e}")
        time.sleep(30)

threading.Thread(target=ad_cleaner, daemon=True).start()

# --- ПРОВЕРКА ПОДПИСКИ ---
def check_subscription(user_id, channel_id):
    try:
        result = api("getChatMember", {"chat_id": channel_id, "user_id": user_id})
        if result.get('ok'):
            status = result['result']['status']
            return status in ['member', 'administrator', 'creator']
        return False
    except:
        return False

def get_channel_link(channel_id):
    try:
        result = api("getChat", {"chat_id": channel_id})
        if result.get('ok'):
            username = result['result'].get('username')
            if username:
                return f"https://t.me/{username}"
            invite_link = result['result'].get('invite_link')
            if invite_link:
                return invite_link
        return None
    except:
        return None

# --- КЛАВИАТУРЫ (С TG PREMIUM ЭМОДЗИ) ---
def main_kb(uid):
    kb = [
        [{"text": "🎮 Игры", "callback_data": "menu_games", "icon_custom_emoji_id": "5938413566624272793"}],
        [{"text": "👤 Профиль", "callback_data": "menu_prof", "icon_custom_emoji_id": "6032693626394382504"},
         {"text": "❓ Помощь", "callback_data": "menu_help", "icon_custom_emoji_id": "6030622631818956594"}]
    ]
    if is_admin(uid):
        kb.append([{"text": "⚡ Админ панель", "callback_data": "adm_root", "icon_custom_emoji_id": "6030445631921721471"}])
    return {"inline_keyboard": kb}

def admin_kb(uid):
    kb = [
        [{"text": "📢 Рассылка", "callback_data": "a_broad", "icon_custom_emoji_id": "6037622221625626773"},
         {"text": "🧹 Очистка", "callback_data": "a_clean", "icon_custom_emoji_id": "6021792097454002931"}],
        [{"text": "📁 Добавить файл", "callback_data": "a_addfile", "icon_custom_emoji_id": "5805648413743651862"},
         {"text": "🔗 ОП", "callback_data": "a_op", "icon_custom_emoji_id": "5962952497197748583"}],
        [{"text": "📰 Реклама", "callback_data": "a_ads", "icon_custom_emoji_id": "5904248647972820334"},
         {"text": "🔨 Бан/Разбан", "callback_data": "a_ban", "icon_custom_emoji_id": "5776227595708273495"}],
        [{"text": "📊 Статистика", "callback_data": "a_stat", "icon_custom_emoji_id": "6032742198179532882"}]
    ]
    if uid == OWNER_ID:
        kb.append([{"text": "👑 Управление админами", "callback_data": "a_mng", "icon_custom_emoji_id": "6032636795387121097"}])
    kb.append([{"text": "🔙 Назад", "callback_data": "to_main"}])
    return {"inline_keyboard": kb}

def games_kb():
    return {
        "inline_keyboard": [
            [{"text": "🔫 Standoff 2", "callback_data": "game_so2", "icon_custom_emoji_id": "5393134637667094112"}],
            [{"text": "🪖 Pubg Mobile", "callback_data": "game_pubg", "icon_custom_emoji_id": "6073605466221451561"}],
            [{"text": "🎲 Other Games", "callback_data": "game_other", "icon_custom_emoji_id": "6095674537196653589"}],
            [{"text": "🔙 Назад", "callback_data": "to_main"}]
        ]
    }

def files_kb(files):
    kb = []
    for f in files[:10]:
        kb.append([{"text": f"📄 {f['name'][:30]}", "callback_data": f"dl_{f['hash']}"}])
    kb.append([{"text": "🔙 Назад", "callback_data": "menu_games"}])
    return {"inline_keyboard": kb}

def back_kb():
    return {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "to_main"}]]}

def perms_kb(target_id):
    return {
        "inline_keyboard": [
            [{"text": "📁 Добавление файлов", "callback_data": f"perm_addfile_{target_id}", "icon_custom_emoji_id": "5805648413743651862"}],
            [{"text": "📢 Рассылка", "callback_data": f"perm_broad_{target_id}", "icon_custom_emoji_id": "6037622221625626773"}],
            [{"text": "👑 Все права", "callback_data": f"perm_all_{target_id}", "icon_custom_emoji_id": "6030445631921721471"}],
            [{"text": "❌ Отмена", "callback_data": "a_mng"}]
        ]
    }

def op_check_kb(channel_id):
    link = get_channel_link(channel_id)
    if link:
        return {
            "inline_keyboard": [
                [{"text": "🔔 ПОДПИСАТЬСЯ", "url": link, "icon_custom_emoji_id": "5927118708873892465"}],
                [{"text": "✅ ПРОВЕРИТЬ", "callback_data": f"op_check_{channel_id}", "icon_custom_emoji_id": "5774022692642492953"}]
            ]
        }
    return None

def channel_check_kb():
    return {
        "inline_keyboard": [
            [{"text": "🔔 ПОДПИСАТЬСЯ", "url": "https://t.me/OfficialPlutonium", "icon_custom_emoji_id": "5927118708873892465"}],
            [{"text": "✅ ПРОВЕРИТЬ", "callback_data": "channel_check", "icon_custom_emoji_id": "5774022692642492953"}]
        ]
    }

def ban_kb(target_id):
    return {
        "inline_keyboard": [
            [{"text": "🔒 ЗАБАНИТЬ", "callback_data": f"ban_do_{target_id}", "icon_custom_emoji_id": "6030563507299160824"}],
            [{"text": "🔓 РАЗБАНИТЬ", "callback_data": f"unban_do_{target_id}", "icon_custom_emoji_id": "6028205772117118673"}],
            [{"text": "❌ Отмена", "callback_data": "a_ban"}]
        ]
    }

def file_footer_kb():
    return {
        "inline_keyboard": [
            [{"text": "💜 Plutonium", "url": "https://t.me/OfficialPlutonium", "icon_custom_emoji_id": "5339472242529045815"}]
        ]
    }

def yes_no_kb():
    return {
        "keyboard": [[{"text": "✅ ДА"}, {"text": "❌ НЕТ"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

def op_setup_kb():
    return {
        "inline_keyboard": [
            [{"text": "✅ Завершить настройку ОП", "callback_data": "op_finish", "icon_custom_emoji_id": "5774022692642492953"}],
            [{"text": "❌ Отмена", "callback_data": "to_main"}]
        ]
    }

# --- ТЕКСТЫ (С TG PREMIUM ЭМОДЗИ) ---
def get_welcome_text():
    return ("<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> Привет!\n"
            "<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> Я храню файлы с канала @OfficialPlutonium\n"
            "<tg-emoji emoji-id=\"6037157012242960559\">👇</tg-emoji> Используй кнопки ниже для навигации")

def get_subscribe_text():
    return ("<tg-emoji emoji-id=\"6037249452824072506\">🔒</tg-emoji> Привет!\n"
            "<tg-emoji emoji-id=\"6039630677182254664\">🔓</tg-emoji> Подпишись на канал @OfficialPlutonium для доступа!")

def get_op_text():
    return ("<tg-emoji emoji-id=\"6037249452824072506\">🔒</tg-emoji> Привет!\n"
            "<tg-emoji emoji-id=\"6039630677182254664\">🔓</tg-emoji> Подпишись для доступа!")

def get_profile_text(uid, first_name, username, downloads):
    return (f"<tg-emoji emoji-id=\"6032693626394382504\">👤</tg-emoji> Профиль\n\n"
            f"<tg-emoji emoji-id=\"5886505193180239900\">🆔</tg-emoji> ID: <code>{uid}</code>\n"
            f"<tg-emoji emoji-id=\"5879770735999717115\">📛</tg-emoji> Имя: {first_name}\n"
            f"<tg-emoji emoji-id=\"5814247475141153332\">🔖</tg-emoji> Username: @{username}\n"
            f"<tg-emoji emoji-id=\"6039802767931871481\">📥</tg-emoji> Файлов получено: {downloads}")

def get_help_text():
    return ("<tg-emoji emoji-id=\"5208957270259425030\">❓</tg-emoji> Помощь\n\n"
            "<tg-emoji emoji-id=\"5794164805065514131\">1️⃣</tg-emoji> Нажми Игры\n"
            "<tg-emoji emoji-id=\"5794085322400733645\">2️⃣</tg-emoji> Выбери игру\n"
            "<tg-emoji emoji-id=\"5794280000383358988\">3️⃣</tg-emoji> Нажми на название чита\n"
            "<tg-emoji emoji-id=\"5794241397217304511\">4️⃣</tg-emoji> Файл автоматически отправится\n\n"
            "<tg-emoji emoji-id=\"6032693626394382504\">📌</tg-emoji> Для админов есть дополнительные функции.")

def get_file_footer(name, description):
    if description:
        return (f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> Ваш Файл: {name}\n\n"
                f"📝 {description}\n\n"
                f"<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> Buy plutonium - @PlutoniumllcBot")
    else:
        return (f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> Ваш Файл: {name}\n\n"
                f"<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> Buy plutonium - @PlutoniumllcBot")

def get_add_file_success(name, description, game, file_link):
    return (f"<tg-emoji emoji-id=\"6039391078136681499\">✅</tg-emoji> Файл добавлен!\n\n"
            f"<tg-emoji emoji-id=\"5257965174979042426\">📄</tg-emoji> Название: {name}\n"
            f"<tg-emoji emoji-id=\"5938413566624272793\">📝</tg-emoji> Описание: {description}\n"
            f"<tg-emoji emoji-id=\"6028171274939797252\">🎮</tg-emoji> Игра: {game.upper()}\n"
            f"<tg-emoji emoji-id=\"5974220038956124904\">🔗</tg-emoji> Ссылка: {file_link}\n"
            f"<tg-emoji emoji-id=\"6039573425268201570\">📥</tg-emoji> Скачиваний: 0")

def get_add_file_prompt():
    return ("<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> Отправь файл\n\n"
            "<tg-emoji emoji-id=\"6037373985400819577\">👤</tg-emoji> В подписи укажи:\n"
            "Название | #игра | Описание\n\n"
            "<tg-emoji emoji-id=\"6039348811363520645\">💜</tg-emoji> Пример: Aimbot | #standoff | Лучший чит для Standoff 2\n\n"
            "<tg-emoji emoji-id=\"6041730074376410123\">☃️</tg-emoji> Доступные игры:\n"
            "#standoff - Standoff 2\n"
            "#pubg - Pubg Mobile\n"
            "#other - Other Games")

def get_broadcast_prompt():
    return ("<tg-emoji emoji-id=\"6039422865189638057\">📢</tg-emoji> Рассылка\n\n"
            "<tg-emoji emoji-id=\"5904248647972820334\">😎</tg-emoji> Отправь сообщение для рассылки.\n\n"
            "<tg-emoji emoji-id=\"6028338546736107668\">🤝</tg-emoji> Поддерживается TG Premium эмодзи.\n\n"
            "/cancel - отмена")

def get_broadcast_success(sent):
    return (f"<tg-emoji emoji-id=\"5774022692642492953\">✅</tg-emoji> Рассылка завершена!\n\n"
            f"<tg-emoji emoji-id=\"6030776052345737530\">💜</tg-emoji> Отправлено: {sent} пользователям")

def get_ad_prompt():
    return ("<tg-emoji emoji-id=\"6039422865189638057\">📢</tg-emoji> Отправь пост для рекламы.\n\n"
            "<tg-emoji emoji-id=\"5904248647972820334\">🤝</tg-emoji> Поддерживаются фото, видео, текст")

def get_ad_time_prompt():
    return ("<tg-emoji emoji-id=\"6039454987250044861\">⏱️</tg-emoji> Введи время в часах (от 1 до 72):\n\nПример: 24")

def get_ad_success(sent, hours):
    return (f"<tg-emoji emoji-id=\"5938252440926163756\">✅</tg-emoji> Реклама отправлена {sent} пользователям\n\n"
            f"<tg-emoji emoji-id=\"5891100675042974129\">🦈</tg-emoji> Удаление через {hours} часов")

def get_op_target_prompt():
    return ("<tg-emoji emoji-id=\"6028171274939797252\">🔗</tg-emoji> Создание ОП\n\n"
            "<tg-emoji emoji-id=\"5895364284782743985\">🦍</tg-emoji> Введи количество подписчиков, которое нужно набрать:\n\n"
            "Пример: 100")

def get_op_link_prompt():
    return ("<tg-emoji emoji-id=\"6028171274939797252\">🔗</tg-emoji> Отправь ссылку на канал или ID канала:\n\n"
            "Примеры:\n"
            "https://t.me/канал\n"
            "-1001234567890")

def get_op_success(channel_id, link, target):
    return (f"<tg-emoji emoji-id=\"5938252440926163756\">✅</tg-emoji> ОП создана!\n\n"
            f"<tg-emoji emoji-id=\"5776424837786374634\">⭐</tg-emoji> Канал: {link}\n"
            f"<tg-emoji emoji-id=\"6028171274939797252\">🎯</tg-emoji> Нужно набрать: {target} подписчиков\n"
            f"<tg-emoji emoji-id=\"6039573425268201570\">📊</tg-emoji> Текущий счетчик: 0\n\n"
            f"Когда наберется {target} подписчиков, ОП автоматически отключится.")

def get_ban_prompt():
    return ("<tg-emoji emoji-id=\"6030563507299160824\">🚫</tg-emoji> Бан/Разбан пользователя\n\n"
            "<tg-emoji emoji-id=\"6028205772117118673\">😎</tg-emoji> Отправь ID или username.\n\n"
            "<tg-emoji emoji-id=\"5774022692642492953\">🤍</tg-emoji> Пример: 1471307057 или @username")

def get_admin_prompt():
    return ("<tg-emoji emoji-id=\"5924722061288150929\">👑</tg-emoji> Управление админами\n\n"
            "<tg-emoji emoji-id=\"6028205772117118673\">💜</tg-emoji> Отправь ID или username.\n\n"
            "<tg-emoji emoji-id=\"5774022692642492953\">✅</tg-emoji> Пример: 1471307057 или @username")

def get_ban_success(target_id):
    return f"<tg-emoji emoji-id=\"6030563507299160824\">✅</tg-emoji> Пользователь {target_id} забанен"
    
def get_unban_success(target_id):
    return f"<tg-emoji emoji-id=\"6028205772117118673\">✅</tg-emoji> Пользователь {target_id} разбанен"

def get_db_prompt():
    return ("<tg-emoji emoji-id=\"6039573425268201570\">📦</tg-emoji> Создаю бэкап базы данных...\n"
            "<tg-emoji emoji-id=\"6039454987250044861\">⏱️</tg-emoji> Подожди немного...")

def get_db_error():
    return "<tg-emoji emoji-id=\"6030563507299160824\">❌</tg-emoji> Ошибка при создании бэкапа базы данных"

# --- ФУНКЦИИ ДЛЯ РАССЫЛКИ ---
def save_broadcast_message(user_id, message, chat_id):
    try:
        msg_data = {'type': None}
        
        if 'text' in message:
            msg_data['type'] = 'text'
            msg_data['text'] = message['text']
            if 'entities' in message:
                msg_data['entities'] = message['entities']
                
        elif 'photo' in message:
            msg_data['type'] = 'photo'
            msg_data['photo'] = message['photo']
            msg_data['caption'] = message.get('caption', '')
            if 'caption_entities' in message:
                msg_data['caption_entities'] = message['caption_entities']
                
        elif 'video' in message:
            msg_data['type'] = 'video'
            msg_data['video'] = message['video']['file_id']
            msg_data['caption'] = message.get('caption', '')
            if 'caption_entities' in message:
                msg_data['caption_entities'] = message['caption_entities']
                
        elif 'document' in message:
            msg_data['type'] = 'document'
            msg_data['document'] = message['document']['file_id']
            msg_data['caption'] = message.get('caption', '')
            if 'caption_entities' in message:
                msg_data['caption_entities'] = message['caption_entities']
        
        elif 'animation' in message:
            msg_data['type'] = 'animation'
            msg_data['animation'] = message['animation']['file_id']
            msg_data['caption'] = message.get('caption', '')
            if 'caption_entities' in message:
                msg_data['caption_entities'] = message['caption_entities']
        
        if msg_data['type']:
            waiting[f"{user_id}_broadcast"] = json.dumps(msg_data, ensure_ascii=False)
            logger.info(f"Saved broadcast: {msg_data['type']}")
            return True
            
    except Exception as e:
        logger.error(f"Save broadcast error: {e}")
    return False

def send_broadcast(msg_data):
    users = conn.execute("SELECT user_id FROM users WHERE banned = 0").fetchall()
    sent = 0
    msg_type = msg_data.get('type', 'text')
    
    for user in users:
        try:
            if msg_type == 'text':
                data = {"chat_id": user['user_id'], "text": msg_data['text']}
                if msg_data.get('entities'):
                    data["entities"] = msg_data['entities']
                api("sendMessage", data)
            elif msg_type == 'photo':
                data = {
                    "chat_id": user['user_id'],
                    "photo": msg_data['photo'][-1]['file_id']
                }
                if msg_data.get('caption'):
                    data["caption"] = msg_data['caption']
                if msg_data.get('caption_entities'):
                    data["caption_entities"] = msg_data['caption_entities']
                api("sendPhoto", data)
            elif msg_type == 'video':
                data = {"chat_id": user['user_id'], "video": msg_data['video']}
                if msg_data.get('caption'):
                    data["caption"] = msg_data['caption']
                if msg_data.get('caption_entities'):
                    data["caption_entities"] = msg_data['caption_entities']
                api("sendVideo", data)
            elif msg_type == 'document':
                data = {"chat_id": user['user_id'], "document": msg_data['document']}
                if msg_data.get('caption'):
                    data["caption"] = msg_data['caption']
                if msg_data.get('caption_entities'):
                    data["caption_entities"] = msg_data['caption_entities']
                api("sendDocument", data)
            elif msg_type == 'animation':
                data = {"chat_id": user['user_id'], "animation": msg_data['animation']}
                if msg_data.get('caption'):
                    data["caption"] = msg_data['caption']
                if msg_data.get('caption_entities'):
                    data["caption_entities"] = msg_data['caption_entities']
                api("sendAnimation", data)
            sent += 1
        except Exception as e:
            logger.error(f"Broadcast error to {user['user_id']}: {e}")
        time.sleep(0.05)
    
    return sent

# --- ХРАНИЛИЩА ---
waiting = {}
processed_hashes = set()
op_temp = {}  # Временное хранение для создания ОП

# --- ФУНКЦИЯ ПРОВЕРКИ ДОСТУПА С ПОДПИСКОЙ ---
def check_and_enter(uid, chat_id, message_id=None):
    """Проверяет подписки и возвращает True если можно войти"""
    # Проверка бана
    user = conn.execute("SELECT banned FROM users WHERE user_id = ?", (uid,)).fetchone()
    if user and user['banned']:
        api("sendMessage", {"chat_id": uid, "text": "⛔ Вы забанены!"})
        return False
    
    # Проверка подписки на основной канал
    if not check_subscription(uid, CHANNEL_ID):
        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": get_subscribe_text(), "parse_mode": "HTML", 
                          "reply_markup": channel_check_kb()})
        return False
    
    # Проверка ОП
    op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
    if op:
        if not check_subscription(uid, op['channel_id']):
            link = get_channel_link(op['channel_id'])
            if link:
                api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": get_op_text(), "parse_mode": "HTML", 
                                  "reply_markup": op_check_kb(op['channel_id'])})
            return False
    
    return True

# --- ОБРАБОТКА CALLBACK ---
def handle_cb(cb):
    uid = cb['from']['id']
    cid = cb['message']['chat']['id']
    mid = cb['message']['message_id']
    data = cb['data']
    
    u = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()
    
    # Проверка подписки на основной канал
    if data == "channel_check":
        if check_subscription(uid, CHANNEL_ID):
            api("editMessageCaption", {
                "chat_id": cid, 
                "message_id": mid, 
                "caption": get_welcome_text(), 
                "parse_mode": "HTML", 
                "reply_markup": main_kb(uid)
            })
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "✅ Подписка подтверждена!"})
        else:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Вы еще не подписались!", "show_alert": True})
        return
    
    # Проверка ОП
    if data.startswith("op_check_"):
        try:
            op_channel_id = int(data.split("_")[2])
            if check_subscription(uid, op_channel_id):
                api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "✅ Подписка подтверждена!"})
                api("editMessageCaption", {
                    "chat_id": cid, 
                    "message_id": mid, 
                    "caption": get_welcome_text(), 
                    "parse_mode": "HTML", 
                    "reply_markup": main_kb(uid)
                })
            else:
                api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Вы еще не подписались!", "show_alert": True})
        except:
            pass
        return
    
    # Завершение настройки ОП
    if data == "op_finish":
        if uid not in op_temp:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Нет активной настройки ОП"})
            return
        
        channel_id = op_temp[uid].get('channel_id')
        target = op_temp[uid].get('target')
        
        if not channel_id or not target:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Не все данные заполнены"})
            return
        
        link = get_channel_link(channel_id)
        if link:
            conn.execute("UPDATE op_settings SET active = 0")
            conn.execute("INSERT INTO op_settings (channel_id, target, current, active, link) VALUES (?, ?, 0, 1, ?)", 
                        (channel_id, target, link))
            conn.commit()
            api("sendMessage", {"chat_id": uid, "text": get_op_success(channel_id, link, target), "parse_mode": "HTML"})
            logger.info(f"ОП создана: канал {channel_id}, цель {target}")
        else:
            api("sendMessage", {"chat_id": uid, "text": "❌ Не удалось получить ссылку на канал"})
        
        del op_temp[uid]
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "✅ ОП создана!"})
        return
    
    # Назад в главное меню
    if data == "to_main":
        api("editMessageCaption", {
            "chat_id": cid, 
            "message_id": mid, 
            "caption": get_welcome_text(), 
            "parse_mode": "HTML", 
            "reply_markup": main_kb(uid)
        })
        return
    
    # Профиль
    if data == "menu_prof":
        api("editMessageCaption", {
            "chat_id": cid, 
            "message_id": mid, 
            "caption": get_profile_text(uid, u['first_name'], u['username'], u['downloads']), 
            "parse_mode": "HTML", 
            "reply_markup": back_kb()
        })
        return
    
    # Помощь
    if data == "menu_help":
        api("editMessageCaption", {
            "chat_id": cid, 
            "message_id": mid, 
            "caption": get_help_text(), 
            "parse_mode": "HTML", 
            "reply_markup": back_kb()
        })
        return
    
    # Меню игр
    if data == "menu_games":
        api("editMessageCaption", {
            "chat_id": cid, 
            "message_id": mid, 
            "caption": "🎮 Выберите игру:", 
            "reply_markup": games_kb()
        })
        return
    
    # Выбор игры
    if data.startswith("game_"):
        game_map = {"so2": "standoff", "pubg": "pubg", "other": "other"}
        game_code = data.split("_")[1]
        game_name = game_map.get(game_code, "other")
        
        files = conn.execute("SELECT * FROM files WHERE game = ? ORDER BY ts DESC LIMIT 10", (game_name,)).fetchall()
        if files:
            cap = f"🎮 {game_name.upper()}\n\n📂 Файлы:"
            api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": cap, "reply_markup": files_kb(files)})
        else:
            cap = f"🎮 {game_name.upper()}\n\n📂 Файлов пока нет"
            api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": cap, "reply_markup": back_kb()})
        return
    
    # Скачивание файла
    if data.startswith("dl_"):
        f_hash = data.split("_")[1]
        f = conn.execute("SELECT * FROM files WHERE hash = ?", (f_hash,)).fetchone()
        if f:
            cap = get_file_footer(f['name'], f['description'])
            api("copyMessage", {
                "chat_id": cid,
                "from_chat_id": STORAGE_CHANNEL_ID,
                "message_id": f['file_id'],
                "caption": cap,
                "parse_mode": "HTML",
                "reply_markup": file_footer_kb()
            })
            conn.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (uid,))
            conn.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (f_hash,))
            conn.commit()
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"✅ {f['name']} отправлен!"})
        return
    
    # Админ панель
    if data == "adm_root":
        if not is_admin(uid):
            return
        api("editMessageCaption", {
            "chat_id": cid, 
            "message_id": mid, 
            "caption": "⚡ Админ панель Plutonium", 
            "reply_markup": admin_kb(uid)
        })
        return
    
    # Статистика
    if data == "a_stat":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        uc = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        dc = conn.execute("SELECT SUM(downloads) FROM users").fetchone()[0] or 0
        fc = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"👥 Юзеров: {uc}\n📥 Скачано: {dc}\n📁 Файлов: {fc}", "show_alert": True})
        return
    
    # Очистка неактивных
    if data == "a_clean":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        now = int(time.time())
        deleted = conn.execute("DELETE FROM users WHERE last_active < ? AND user_id NOT IN (SELECT user_id FROM admins)", 
                              (now - 30*24*3600,)).rowcount
        conn.commit()
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"Удалено неактивных: {deleted}", "show_alert": True})
        return
    
    # Добавить файл
    if data == "a_addfile":
        if not has_perm(uid, "addfile") and not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "addfile"
        api("sendMessage", {"chat_id": cid, "text": get_add_file_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь файл"})
        return
    
    # ОП (обязательная подписка)
    if data == "a_op":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "op_target"
        api("sendMessage", {"chat_id": cid, "text": get_op_target_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Введи количество подписчиков"})
        return
    
    # Реклама
    if data == "a_ads":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "ad_post"
        api("sendMessage", {"chat_id": cid, "text": get_ad_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь пост"})
        return
    
    # Бан/Разбан
    if data == "a_ban":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "ban_user"
        api("sendMessage", {"chat_id": cid, "text": get_ban_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь ID или username"})
        return
    
    # Рассылка
    if data == "a_broad":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "broadcast"
        api("sendMessage", {"chat_id": cid, "text": get_broadcast_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь сообщение"})
        return
    
    # Управление админами
    if data == "a_mng":
        if uid != OWNER_ID:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Только для владельца", "show_alert": True})
            return
        waiting[uid] = "add_admin"
        api("sendMessage", {"chat_id": cid, "text": get_admin_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь ID или username"})
        return
    
    # Выбор прав для админа
    if data.startswith("perm_"):
        if uid != OWNER_ID:
            return
        parts = data.split("_")
        perm_type = parts[1]
        target_id = int(parts[2])
        
        if perm_type == "addfile":
            perms = json.dumps(["addfile"])
            conn.execute("INSERT OR REPLACE INTO admins (user_id, perms, added_by) VALUES (?, ?, ?)", (target_id, perms, uid))
            api("sendMessage", {"chat_id": cid, "text": f"✅ Админу {target_id} выдано право на добавление файлов"})
        elif perm_type == "broad":
            perms = json.dumps(["addfile", "broadcast"])
            conn.execute("INSERT OR REPLACE INTO admins (user_id, perms, added_by) VALUES (?, ?, ?)", (target_id, perms, uid))
            api("sendMessage", {"chat_id": cid, "text": f"✅ Админу {target_id} выданы права: добавление файлов, рассылка"})
        elif perm_type == "all":
            perms = json.dumps(["all"])
            conn.execute("INSERT OR REPLACE INTO admins (user_id, perms, added_by) VALUES (?, ?, ?)", (target_id, perms, uid))
            api("sendMessage", {"chat_id": cid, "text": f"✅ Админу {target_id} выданы все права"})
        
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ Админ панель Plutonium", "reply_markup": admin_kb(uid)})
        return
    
    # Забанить
    if data.startswith("ban_do_"):
        target_id = int(data.split("_")[2])
        if target_id == uid:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Нельзя забанить себя!", "show_alert": True})
            return
        if target_id == OWNER_ID:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Нельзя забанить владельца!", "show_alert": True})
            return
        conn.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        api("sendMessage", {"chat_id": cid, "text": get_ban_success(target_id), "parse_mode": "HTML"})
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ Админ панель Plutonium", "reply_markup": admin_kb(uid)})
        return
    
    # Разбанить
    if data.startswith("unban_do_"):
        target_id = int(data.split("_")[2])
        conn.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        api("sendMessage", {"chat_id": cid, "text": get_unban_success(target_id), "parse_mode": "HTML"})
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ Админ панель Plutonium", "reply_markup": admin_kb(uid)})
        return

# --- ОСНОВНОЙ ЦИКЛ ---
def main():
    logger.info("🚀 Запуск Plutonium Bot")
    logger.info(f"👑 Владелец: {OWNER_ID}")
    logger.info(f"🗄️ База: {'Turso' if USE_TURSO else 'Локальная SQLite'}")
    api("deleteWebhook", {"drop_pending_updates": True})
    offset = 0
    
    while True:
        try:
            upds = api("getUpdates", {"offset": offset, "timeout": 20})
            if not upds.get('ok'):
                time.sleep(1)
                continue
            
            for u in upds['result']:
                offset = u['update_id'] + 1
                
                if 'callback_query' in u:
                    handle_cb(u['callback_query'])
                    continue
                
                if 'message' not in u:
                    continue
                
                m = u['message']
                uid = m['from']['id']
                chat_id = m['chat']['id']
                text = m.get('text', '')
                username = m['from'].get('username', '')
                first_name = m['from'].get('first_name', 'User')
                
                # Регистрация
                if not conn.execute("SELECT 1 FROM users WHERE user_id = ?", (uid,)).fetchone():
                    conn.execute("INSERT INTO users (user_id, username, first_name, last_active) VALUES (?, ?, ?, ?)", 
                                 (uid, username, first_name, int(time.time())))
                    conn.commit()
                
                # Обновляем активность
                conn.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (int(time.time()), uid))
                conn.commit()
                
                # Обновляем счетчик ОП (проверяем подписку на канал)
                op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
                if op:
                    if check_subscription(uid, op['channel_id']):
                        new_cur = op['current'] + 1
                        conn.execute("UPDATE op_settings SET current = ? WHERE id = ?", (new_cur, op['id']))
                        if new_cur >= op['target']:
                            conn.execute("UPDATE op_settings SET active = 0 WHERE id = ?", (op['id'],))
                            logger.info(f"ОП выполнена! Набрано {new_cur} из {op['target']}")
                        conn.commit()
                      # --- КОМАНДА ПОЛУЧЕНИЯ БАЗЫ ---
                if text == "/getdb":
                    if not is_admin(uid):
                        api("sendMessage", {"chat_id": uid, "text": "⛔ Нет прав!"})
                        continue
                    
                    api("sendMessage", {"chat_id": uid, "text": get_db_prompt(), "parse_mode": "HTML"})
                    
                    try:
                        if USE_TURSO:
                            temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
                            temp_db.close()
                            
                            backup_conn = sqlite3.connect(temp_db.name)
                            conn.backup(backup_conn)
                            backup_conn.close()
                            
                            with open(temp_db.name, 'rb') as f:
                                api("sendDocument", {
                                    "chat_id": uid,
                                    "document": f.read(),
                                    "caption": f"📦 Бэкап\n🕐 {time.strftime('%Y-%m-%d %H:%M:%S')}"
                                })
                            os.unlink(temp_db.name)
                        else:
                            with open(DB_PATH, 'rb') as f:
                                api("sendDocument", {
                                    "chat_id": uid,
                                    "document": f.read(),
                                    "caption": f"📦 Бэкап\n🕐 {time.strftime('%Y-%m-%d %H:%M:%S')}"
                                })
                    except Exception as e:
                        logger.error(f"GetDB error: {e}")
                        api("sendMessage", {"chat_id": uid, "text": get_db_error(), "parse_mode": "HTML"})
                    continue
                
                # --- ОЖИДАНИЯ ---
                
                # Добавление файла
                if waiting.get(uid) == "addfile" and 'document' in m:
                    cap = m.get('caption', '')
                    game = "other"
                    if "#standoff" in cap.lower():
                        game = "standoff"
                    elif "#pubg" in cap.lower():
                        game = "pubg"
                    elif "#other" in cap.lower():
                        game = "other"
                    
                    parts = cap.split('|')
                    name = parts[0].strip() if len(parts) > 0 else "File"
                    description = parts[2].strip() if len(parts) > 2 else ""
                    
                    try:
                        copy_result = api("copyMessage", {
                            "chat_id": STORAGE_CHANNEL_ID,
                            "from_chat_id": chat_id,
                            "message_id": m['message_id']
                        }, retry=3)
                        
                        if copy_result.get('ok'):
                            stored_msg_id = copy_result['result']['message_id']
                            file_hash = secrets.token_urlsafe(6)
                            conn.execute("INSERT INTO files (hash, file_id, name, description, game, ts, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                         (file_hash, stored_msg_id, name, description, game, int(time.time()), uid))
                            conn.commit()
                            
                            bot_info = api("getMe")
                            bot_username = bot_info.get('result', {}).get('username', 'plutoniumfilesBot')
                            file_link = f"https://t.me/{bot_username}?start={file_hash}"
                            api("sendMessage", {"chat_id": uid, "text": get_add_file_success(name, description, game, file_link), "parse_mode": "HTML"})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Ошибка сохранения файла"})
                    except Exception as e:
                        logger.error(f"Save error: {e}")
                        api("sendMessage", {"chat_id": uid, "text": f"❌ Ошибка: {e}"})
                    
                    waiting[uid] = None
                    continue
                
                # ОП - ввод количества подписчиков
                elif waiting.get(uid) == "op_target" and text and text.isdigit():
                    target = int(text)
                    if target <= 0:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Введи число больше 0"})
                        continue
                    
                    op_temp[uid] = {'target': target}
                    waiting[uid] = "op_link"
                    api("sendMessage", {"chat_id": uid, "text": get_op_link_prompt(), "parse_mode": "HTML"})
                    continue
                
                # ОП - ввод ссылки или ID канала
                elif waiting.get(uid) == "op_link" and text:
                    channel_input = text.strip()
                    channel_id = None
                    
                    if channel_input.startswith("https://t.me/"):
                        username = channel_input.replace("https://t.me/", "").split("?")[0]
                        try:
                            chat_info = api("getChat", {"chat_id": f"@{username}"})
                            if chat_info.get('ok'):
                                channel_id = chat_info['result']['id']
                        except:
                            pass
                    elif channel_input.startswith("-100") and channel_input.lstrip("-").isdigit():
                        channel_id = int(channel_input)
                    elif channel_input.isdigit():
                        channel_id = int(channel_input)
                    
                    if not channel_id:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Не удалось определить ID канала.\n\nОтправь ссылку вида:\nhttps://t.me/канал\nИли ID: -1001234567890"})
                        continue
                    
                    check_result = api("getChat", {"chat_id": channel_id})
                    if not check_result.get('ok'):
                        api("sendMessage", {"chat_id": uid, "text": f"❌ Канал не найден!\n\nОшибка: {check_result.get('description', 'Неизвестная ошибка')}"})
                        continue
                    
                    op_temp[uid]['channel_id'] = channel_id
                    
                    link = get_channel_link(channel_id) or str(channel_id)
                    api("sendMessage", {
                        "chat_id": uid, 
                        "text": f"✅ Канал найден!\n\n📢 Канал: {link}\n🎯 Цель: {op_temp[uid]['target']} подписчиков\n\nНажми кнопку для завершения настройки ОП.",
                        "reply_markup": op_setup_kb()
                    })
                    waiting[uid] = None
                    continue
                
                # Реклама
                elif waiting.get(uid) == "ad_post" and (text or m.get('caption') or m.get('photo')):
                    waiting[uid] = "ad_time"
                    msg_data = {
                        'message_id': m['message_id'],
                        'chat_id': chat_id
                    }
                    if 'text' in m:
                        msg_data['text'] = m['text']
                        if 'entities' in m:
                            msg_data['entities'] = m['entities']
                    elif 'caption' in m:
                        msg_data['caption'] = m['caption']
                        if 'caption_entities' in m:
                            msg_data['caption_entities'] = m['caption_entities']
                        if 'photo' in m:
                            msg_data['photo'] = m['photo']
                    waiting[f"{uid}_msg"] = json.dumps(msg_data)
                    api("sendMessage", {"chat_id": uid, "text": get_ad_time_prompt(), "parse_mode": "HTML"})
                    continue
                
                elif waiting.get(uid) == "ad_time" and text and text.isdigit():
                    hours = int(text)
                    if 1 <= hours <= 72:
                        expire = int(time.time()) + hours * 3600
                        msg_data = json.loads(waiting.get(f"{uid}_msg", "{}"))
                        
                        conn.execute("INSERT INTO ads (msg_id, chat_id, expire, message_data) VALUES (?, ?, ?, ?)", 
                                    (msg_data['message_id'], chat_id, expire, waiting.get(f"{uid}_msg")))
                        conn.commit()
                        
                        users = conn.execute("SELECT user_id FROM users WHERE banned = 0").fetchall()
                        sent = 0
                        for user in users:
                            try:
                                if 'text' in msg_data:
                                    api("sendMessage", {"chat_id": user['user_id'], "text": msg_data['text']})
                                elif 'caption' in msg_data:
                                    api("sendPhoto", {
                                        "chat_id": user['user_id'],
                                        "photo": msg_data['photo'][-1]['file_id'],
                                        "caption": msg_data['caption']
                                    })
                                sent += 1
                            except:
                                pass
                            time.sleep(0.05)
                        
                        api("sendMessage", {"chat_id": uid, "text": get_ad_success(sent, hours), "parse_mode": "HTML"})
                        waiting[uid] = None
                        if f"{uid}_msg" in waiting:
                            del waiting[f"{uid}_msg"]
                    else:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Введи число от 1 до 72"})
                    continue
                
                # Бан/Разбан
                elif waiting.get(uid) == "ban_user" and text:
                    target = text.strip().replace('@', '')
                    try:
                        target_id = int(target) if target.isdigit() else None
                        if not target_id:
                            user = conn.execute("SELECT user_id FROM users WHERE username = ?", (target,)).fetchone()
                            target_id = user['user_id'] if user else None
                        
                        if target_id:
                            waiting[uid] = None
                            api("sendMessage", {"chat_id": uid, "text": f"👤 Пользователь: {target_id}\n\nВыбери действие:", 
                                               "reply_markup": ban_kb(target_id)})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Пользователь не найден"})
                            waiting[uid] = None
                    except:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Ошибка"})
                        waiting[uid] = None
                    continue
                
                      # Рассылка
                elif waiting.get(uid) == "broadcast" and (text or m.get('caption') or m.get('photo')):
                    if text == "/cancel":
                        waiting[uid] = None
                        api("sendMessage", {"chat_id": uid, "text": "✅ Рассылка отменена"})
                        continue
                    
                    if save_broadcast_message(uid, m, chat_id):
                        waiting[uid] = "broadcast_confirm"
                        preview = "📎 Сообщение сохранено"
                        if 'text' in m:
                            preview = m['text'][:100]
                        elif 'caption' in m:
                            preview = m['caption'][:100]
                        elif 'photo' in m:
                            preview = "📸 Фото"
                        
                        api("sendMessage", {"chat_id": uid, "text": f"✅ Сохранено!\n\n{preview}\n\nОтправить всем? (ДА/НЕТ)", "reply_markup": yes_no_kb()})
                    else:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Ошибка сохранения сообщения"})
                        waiting[uid] = None
                    continue
                
                elif waiting.get(uid) == "broadcast_confirm" and text in ["✅ ДА", "❌ НЕТ"]:
                    if text == "✅ ДА":
                        msg_data_str = waiting.get(f"{uid}_broadcast")
                        if msg_data_str:
                            msg_data = json.loads(msg_data_str)
                            sent = send_broadcast(msg_data)
                            api("sendMessage", {"chat_id": uid, "text": get_broadcast_success(sent), "parse_mode": "HTML"})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Ошибка: нет сообщения"})
                    else:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Отменено"})
                    
                    if f"{uid}_broadcast" in waiting:
                        del waiting[f"{uid}_broadcast"]
                    waiting[uid] = None
                    continue
                
                # Управление админами
                elif waiting.get(uid) == "add_admin" and text and uid == OWNER_ID:
                    target = text.strip().replace('@', '')
                    try:
                        target_id = int(target) if target.isdigit() else None
                        if not target_id:
                            user = conn.execute("SELECT user_id FROM users WHERE username = ?", (target,)).fetchone()
                            target_id = user['user_id'] if user else None
                        
                        if target_id:
                            if target_id == uid:
                                api("sendMessage", {"chat_id": uid, "text": "❌ Нельзя управлять собой!"})
                                waiting[uid] = None
                                continue
                            admin = conn.execute("SELECT * FROM admins WHERE user_id = ?", (target_id,)).fetchone()
                            if admin:
                                conn.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
                                api("sendMessage", {"chat_id": uid, "text": f"✅ Админ {target_id} удален"})
                            else:
                                api("sendMessage", {"chat_id": uid, "text": f"👑 Выбери права для {target_id}:", "reply_markup": perms_kb(target_id)})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Пользователь не найден"})
                    except Exception as e:
                        api("sendMessage", {"chat_id": uid, "text": f"❌ Ошибка: {e}"})
                    waiting[uid] = None
                    continue
                
                # --- ОСНОВНЫЕ КОМАНДЫ ---
                
                # /start - СНАЧАЛА ПРОВЕРКА ПОДПИСКИ, ПОТОМ МЕНЮ
                if text == "/start":
                    # Проверка подписки на основной канал
                    if not check_subscription(uid, CHANNEL_ID):
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": get_subscribe_text(), "parse_mode": "HTML", 
                                          "reply_markup": channel_check_kb()})
                        continue
                    
                    # Проверка ОП
                    op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
                    if op:
                        if not check_subscription(uid, op['channel_id']):
                            link = get_channel_link(op['channel_id'])
                            if link:
                                api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": get_op_text(), "parse_mode": "HTML", 
                                                  "reply_markup": op_check_kb(op['channel_id'])})
                            continue
                    
                    # Только после всех проверок показываем меню
                    api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": get_welcome_text(), "parse_mode": "HTML", "reply_markup": main_kb(uid)})
                
                # Ссылка на файл - ТОЖЕ СНАЧАЛА ПРОВЕРКА ПОДПИСКИ
                elif text.startswith("/start "):
                    # Сначала проверяем подписки
                    if not check_subscription(uid, CHANNEL_ID):
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": get_subscribe_text(), "parse_mode": "HTML", 
                                          "reply_markup": channel_check_kb()})
                        continue
                    
                    op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
                    if op:
                        if not check_subscription(uid, op['channel_id']):
                            link = get_channel_link(op['channel_id'])
                            if link:
                                api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": get_op_text(), "parse_mode": "HTML", 
                                                  "reply_markup": op_check_kb(op['channel_id'])})
                            continue
                    
                    f_hash = text.split(" ")[1]
                    
                    # Защита от дублей
                    if f_hash in processed_hashes:
                        continue
                    processed_hashes.add(f_hash)
                    threading.Timer(5, lambda: processed_hashes.discard(f_hash)).start()
                    
                    f = conn.execute("SELECT * FROM files WHERE hash = ?", (f_hash,)).fetchone()
                    if f:
                        api("sendMessage", {"chat_id": uid, "text": "📤 Отправляю файл!", "parse_mode": "HTML"})
                        
                        cap = get_file_footer(f['name'], f['description'])
                        api("copyMessage", {
                            "chat_id": uid,
                            "from_chat_id": STORAGE_CHANNEL_ID,
                            "message_id": f['file_id'],
                            "caption": cap,
                            "parse_mode": "HTML",
                            "reply_markup": file_footer_kb()
                        })
                        conn.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (uid,))
                        conn.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (f_hash,))
                        conn.commit()
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
