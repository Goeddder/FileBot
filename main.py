import os
import sqlite3
import secrets
import json
import logging
import urllib.request
import time
import threading
import re
import tempfile
import subprocess

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
        logger.error("❌ libsql_experimental не установлен, использую локальную SQLite")
        USE_TURSO = False
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
else:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    logger.info("✅ Подключено к локальной SQLite")

conn.row_factory = sqlite3.Row

def init_db():
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, file_id INTEGER, name TEXT, description TEXT, game TEXT, ts INTEGER, created_by INTEGER, downloads INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, downloads INTEGER DEFAULT 0, banned INTEGER DEFAULT 0, last_active INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, perms TEXT, added_by INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS op_settings (id INTEGER PRIMARY KEY, channel_id INTEGER, target INTEGER, current INTEGER DEFAULT 0, active INTEGER DEFAULT 0, link TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS ads (msg_id INTEGER PRIMARY KEY, chat_id INTEGER, expire INTEGER, message_data TEXT)")
    c.execute("INSERT OR IGNORE INTO admins (user_id, perms, added_by) VALUES (?, ?, ?)", (OWNER_ID, '["all"]', OWNER_ID))
    conn.commit()
    logger.info("✅ База данных готова")

init_db()

# --- ФУНКЦИИ API ---
def api(method, data=None):
    url = f"{API_URL}/{method}"
    max_retries = 3
    for attempt in range(max_retries):
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
            logger.error(f"API error (attempt {attempt+1}): {e}")
            if attempt == max_retries - 1:
                return {'ok': False}
            time.sleep(2 ** attempt)
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
        now = int(time.time())
        expired = conn.execute("SELECT * FROM ads WHERE expire < ?", (now,)).fetchall()
        for ad in expired:
            api("deleteMessage", {"chat_id": ad['chat_id'], "message_id": ad['msg_id']})
            conn.execute("DELETE FROM ads WHERE msg_id = ?", (ad['msg_id'],))
        conn.commit()
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
    except Exception as e:
        logger.error(f"Check subscription error: {e}")
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
    except Exception as e:
        logger.error(f"Get channel link error: {e}")
        return None

# --- КЛАВИАТУРЫ ---
def main_kb(uid):
    kb = [
        [{"text": "🎮 Игры", "callback_data": "menu_games"}],
        [{"text": "👤 Профиль", "callback_data": "menu_prof"},
         {"text": "❓ Помощь", "callback_data": "menu_help"}]
    ]
    if is_admin(uid):
        kb.append([{"text": "⚡ Админ панель", "callback_data": "adm_root"}])
    return {"inline_keyboard": kb}

def admin_kb(uid):
    kb = [
        [{"text": "📢 Рассылка", "callback_data": "a_broad"},
         {"text": "🧹 Очистка", "callback_data": "a_clean"}],
        [{"text": "📁 Добавить файл", "callback_data": "a_addfile"},
         {"text": "🔗 ОП", "callback_data": "a_op"}],
        [{"text": "📰 Реклама", "callback_data": "a_ads"},
         {"text": "🔨 Бан/Разбан", "callback_data": "a_ban"}],
        [{"text": "📊 Статистика", "callback_data": "a_stat"}]
    ]
    if uid == OWNER_ID:
        kb.append([{"text": "👑 Управление админами", "callback_data": "a_mng"}])
    kb.append([{"text": "🔙 Назад", "callback_data": "to_main"}])
    return {"inline_keyboard": kb}

def games_kb():
    return {
        "inline_keyboard": [
            [{"text": "🔫 Standoff 2", "callback_data": "game_so2"}],
            [{"text": "🪖 Pubg Mobile", "callback_data": "game_pubg"}],
            [{"text": "🎲 Other Games", "callback_data": "game_other"}],
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
            [{"text": "📁 Добавление файлов", "callback_data": f"perm_addfile_{target_id}"}],
            [{"text": "📢 Рассылка", "callback_data": f"perm_broad_{target_id}"}],
            [{"text": "👑 Все права", "callback_data": f"perm_all_{target_id}"}],
            [{"text": "❌ Отмена", "callback_data": "a_mng"}]
        ]
    }

def op_check_kb(channel_id):
    link = get_channel_link(channel_id)
    if link:
        return {
            "inline_keyboard": [
                [{"text": "🔔 ПОДПИСАТЬСЯ", "url": link}],
                [{"text": "✅ ПРОВЕРИТЬ", "callback_data": f"op_check_{channel_id}"}]
            ]
        }
    return None

def channel_check_kb():
    return {
        "inline_keyboard": [
            [{"text": "🔔 ПОДПИСАТЬСЯ", "url": "https://t.me/OfficialPlutonium"}],
            [{"text": "✅ ПРОВЕРИТЬ", "callback_data": "channel_check"}]
        ]
    }

def ban_kb(target_id):
    return {
        "inline_keyboard": [
            [{"text": "🔒 ЗАБАНИТЬ", "callback_data": f"ban_do_{target_id}"}],
            [{"text": "🔓 РАЗБАНИТЬ", "callback_data": f"unban_do_{target_id}"}],
            [{"text": "❌ Отмена", "callback_data": "a_ban"}]
        ]
    }

def file_footer_kb():
    return {
        "inline_keyboard": [
            [{"text": "💜 Plutonium", "url": "https://t.me/OfficialPlutonium"}]
        ]
    }

def yes_no_kb():
    return {
        "keyboard": [[{"text": "✅ ДА"}, {"text": "❌ НЕТ"}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

# --- ТЕКСТЫ ---
def get_welcome_text():
    return "👋 Привет!\n🙂 Я храню файлы с канала @OfficialPlutonium\n👇 Используй кнопки ниже для навигации"

def get_subscribe_text():
    return "🔒 Привет!\n🔓 Подпишись на канал @OfficialPlutonium для доступа!"

def get_op_text():
    return "🔒 Привет!\n🔓 Подпишись для доступа!"

def get_profile_text(uid, first_name, username, downloads):
    return (f"👤 Профиль\n\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📛 Имя: {first_name}\n"
            f"🔖 Username: @{username}\n"
            f"📥 Файлов получено: {downloads}")

def get_help_text():
    return ("❓ Помощь\n\n"
            "1️⃣ Нажми Игры\n"
            "2️⃣ Выбери игру\n"
            "3️⃣ Нажми на название чита\n"
            "4️⃣ Файл автоматически отправится\n\n"
            "📌 Для админов есть дополнительные функции.")

def get_file_footer(name, description):
    if description:
        return (f"📤 Ваш Файл: {name}\n\n"
                f"📝 {description}\n\n"
                f"🏪 Buy plutonium - @PlutoniumllcBot")
    else:
        return (f"📤 Ваш Файл: {name}\n\n"
                f"🏪 Buy plutonium - @PlutoniumllcBot")

def get_add_file_success(name, description, game, file_link):
    return (f"✅ Файл добавлен!\n\n"
            f"📄 Название: {name}\n"
            f"📝 Описание: {description}\n"
            f"🎮 Игра: {game.upper()}\n"
            f"🔗 Ссылка: {file_link}\n"
            f"📥 Скачиваний: 0\n\n"
            f"📤 При выдаче файла будет:\n"
            f"🏪 Buy plutonium - @PlutoniumllcBot")

def get_add_file_prompt():
    return ("📤 Отправь файл\n\n"
            "👤 В подписи укажи:\n"
            "Название | #игра | Описание\n\n"
            "💜 Пример: Aimbot | #standoff | Лучший чит для Standoff 2\n\n"
            "☃️ Доступные игры:\n"
            "#standoff - Standoff 2\n"
            "#pubg - Pubg Mobile\n"
            "#other - Other Games")

def get_broadcast_prompt():
    return ("📢 Рассылка\n\n"
            "😎 Отправь сообщение для рассылки.\n\n"
            "🤝 Поддерживается TG Premium эмодзи.\n\n"
            "/cancel - отмена")

def get_broadcast_success(sent):
    return f"✅ Рассылка завершена!\n\n💜 Отправлено: {sent} пользователям"

def get_ad_prompt():
    return ("📢 Размещение рекламы\n\n"
            "🤝 Отправь пост для рекламы.\n\n"
            "😂 Поддерживается TG Premium эмодзи.")

def get_ad_time_prompt():
    return ("⏱️ Введи время в часах (от 1 до 72):\n\nПример: 24")

def get_ad_success(sent, hours):
    return f"✅ Реклама отправлена {sent} пользователям\n\n🦈 Удаление через {hours} часов"

def get_op_prompt():
    return ("🔗 Создание ОП\n\n"
            "🦍 Введи ID канала для обязательной подписки.\n\n"
            "🇺🇸 Пример: -1001234567890\n\n"
            "💡 Чтобы получить ID канала:\n"
            "1. Добавь бота @getmyid_bot в канал\n"
            "2. Напиши /start в канале\n"
            "3. Скопируй ID")

def get_op_success(channel_id, link):
    return f"✅ ОП создана!\n\n⭐ Канал ID: {channel_id}\n🔥 Ссылка: {link}"

def get_ban_prompt():
    return ("🚫 Бан/Разбан пользователя\n\n"
            "😎 Отправь ID или username.\n\n"
            "🤍 Пример: 1471307057 или @username")

def get_admin_prompt():
    return ("👑 Управление админами\n\n"
            "💜 Отправь ID или username.\n\n"
            "✅ Пример: 1471307057 или @username")

def get_ban_success(target_id):
    return f"✅ Пользователь {target_id} забанен"
    
def get_unban_success(target_id):
    return f"✅ Пользователь {target_id} разбанен"

def get_db_prompt():
    return ("📦 Выгрузка базы данных\n\n"
            "⏳ Подожди, создаю бэкап...\n"
            "💾 Файл будет отправлен через несколько секунд")

def get_db_error():
    return "❌ Ошибка при создании бэкапа базы данных"

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С СООБЩЕНИЯМИ ---
def save_entities(entities):
    saved_entities = []
    for e in entities:
        entity = {
            'offset': e['offset'],
            'length': e['length'],
            'type': e['type']
        }
        if e['type'] == 'custom_emoji' and 'custom_emoji_id' in e:
            entity['custom_emoji_id'] = e['custom_emoji_id']
        if e['type'] == 'text_link' and 'url' in e:
            entity['url'] = e['url']
        if e['type'] == 'text_mention' and 'user' in e:
            entity['user'] = {'id': e['user']['id']}
        saved_entities.append(entity)
    return saved_entities

def save_broadcast_message(user_id, message, chat_id):
    try:
        msg_data = {'type': None}
        
        if 'text' in message:
            msg_data['type'] = 'text'
            msg_data['text'] = message['text']
            if 'entities' in message:
                msg_data['entities'] = save_entities(message['entities'])
                
        elif 'photo' in message:
            msg_data['type'] = 'photo'
            msg_data['photo'] = message['photo']
            msg_data['caption'] = message.get('caption', '')
            if 'caption_entities' in message:
                msg_data['caption_entities'] = save_entities(message['caption_entities'])
                
        elif 'video' in message:
            msg_data['type'] = 'video'
            msg_data['video'] = message['video']['file_id']
            msg_data['caption'] = message.get('caption', '')
            if 'caption_entities' in message:
                msg_data['caption_entities'] = save_entities(message['caption_entities'])
                
        elif 'document' in message:
            msg_data['type'] = 'document'
            msg_data['document'] = message['document']['file_id']
            msg_data['caption'] = message.get('caption', '')
            if 'caption_entities' in message:
                msg_data['caption_entities'] = save_entities(message['caption_entities'])
        
        elif 'animation' in message:
            msg_data['type'] = 'animation'
            msg_data['animation'] = message['animation']['file_id']
            msg_data['caption'] = message.get('caption', '')
            if 'caption_entities' in message:
                msg_data['caption_entities'] = save_entities(message['caption_entities'])
        
        if msg_data['type']:
            waiting[f"{user_id}_broadcast"] = json.dumps(msg_data, ensure_ascii=False)
            logger.info(f"Saved broadcast message type: {msg_data['type']}")
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
            logger.error(f"Broadcast send error to {user['user_id']}: {e}")
        time.sleep(0.05)
    
    return sent

# --- ХРАНИЛИЩА ---
waiting = {}
processed_hashes = set()

# --- ОБРАБОТКА CALLBACK ---
def handle_cb(cb):
    uid = cb['from']['id']
    cid = cb['message']['chat']['id']
    mid = cb['message']['message_id']
    data = cb['data']
    
    u = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()
    
    if data == "channel_check":
        if check_subscription(uid, CHANNEL_ID):
            api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": get_welcome_text(), "parse_mode": "HTML", "reply_markup": main_kb(uid)})
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "✅ Подписка подтверждена!"})
        else:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Вы еще не подписались!", "show_alert": True})
        return
    
    if data.startswith("op_check_"):
        try:
            op_channel_id = int(data.split("_")[2])
            if check_subscription(uid, op_channel_id):
                api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "✅ Подписка подтверждена!"})
                api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": get_welcome_text(), "parse_mode": "HTML", "reply_markup": main_kb(uid)})
            else:
                api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Вы еще не подписались!", "show_alert": True})
        except:
            pass
        return
    
    if data == "to_main":
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": get_welcome_text(), "parse_mode": "HTML", "reply_markup": main_kb(uid)})
        return
    
    if data == "menu_prof":
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": get_profile_text(uid, u['first_name'], u['username'], u['downloads']), "parse_mode": "HTML", "reply_markup": back_kb()})
        return
    
    if data == "menu_help":
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": get_help_text(), "parse_mode": "HTML", "reply_markup": back_kb()})
        return
    
    if data == "menu_games":
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "🎮 Выберите игру:", "reply_markup": games_kb()})
        return
    
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
    
    if data == "adm_root":
        if not is_admin(uid):
            return
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ Админ панель Plutonium", "reply_markup": admin_kb(uid)})
        return
    
    if data == "a_stat":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        uc = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        dc = conn.execute("SELECT SUM(downloads) FROM users").fetchone()[0] or 0
        fc = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"👥 Юзеров: {uc}\n📥 Скачано: {dc}\n📁 Файлов: {fc}", "show_alert": True})
        return
    
    if data == "a_clean":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        now = int(time.time())
        deleted = conn.execute("DELETE FROM users WHERE last_active < ? AND user_id NOT IN (SELECT user_id FROM admins)", (now - 30*24*3600,)).rowcount
        conn.commit()
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"Удалено неактивных: {deleted}", "show_alert": True})
        return
    
    if data == "a_addfile":
        if not has_perm(uid, "addfile") and not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "addfile"
        api("sendMessage", {"chat_id": cid, "text": get_add_file_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь файл"})
        return
    
    if data == "a_op":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "op_channel_id"
        api("sendMessage", {"chat_id": cid, "text": get_op_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Введи ID канала"})
        return
    
    if data == "a_ads":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "ad_post"
        api("sendMessage", {"chat_id": cid, "text": get_ad_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь пост"})
        return
    
    if data == "a_ban":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "ban_user"
        api("sendMessage", {"chat_id": cid, "text": get_ban_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь ID или username"})
        return
    
    if data == "a_broad":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "broadcast"
        api("sendMessage", {"chat_id": cid, "text": get_broadcast_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь сообщение"})
        return
    
    if data == "a_mng":
        if uid != OWNER_ID:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Только для владельца", "show_alert": True})
            return
        waiting[uid] = "add_admin"
        api("sendMessage", {"chat_id": cid, "text": get_admin_prompt(), "parse_mode": "HTML"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь ID или username"})
        return
    
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
    logger.info(f"📢 Канал подписки ID: {CHANNEL_ID}")
    logger.info(f"💾 Канал хранения ID: {STORAGE_CHANNEL_ID}")
    logger.info(f"🗄️ База данных: {'Turso' if USE_TURSO else 'Локальная SQLite'}")
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
                
                # Проверка бана
                user = conn.execute("SELECT banned FROM users WHERE user_id = ?", (uid,)).fetchone()
                if user and user['banned']:
                    if text == "/start":
                        api("sendMessage", {"chat_id": uid, "text": "⛔ Вы забанены!\nОбратитесь к администратору."})
                    continue
                
                # Регистрация
                if not conn.execute("SELECT 1 FROM users WHERE user_id = ?", (uid,)).fetchone():
                    conn.execute("INSERT INTO users (user_id, username, first_name, last_active) VALUES (?, ?, ?, ?)", 
                                 (uid, username, first_name, int(time.time())))
                    conn.commit()
                
                # Обновляем активность
                conn.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (int(time.time()), uid))
                conn.commit()
                
                # --- КОМАНДА ПОЛУЧЕНИЯ БАЗЫ ДАННЫХ ---
                if text == "/getdb":
                    if not is_admin(uid):
                        api("sendMessage", {"chat_id": uid, "text": "⛔ У вас нет прав для этой команды!"})
                        continue
                    
                    api("sendMessage", {"chat_id": uid, "text": "📦 Выгрузка базы данных\n\n⏳ Подожди, создаю бэкап...\n💾 Файл будет отправлен через несколько секунд", "parse_mode": "HTML"})
                    
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
                                    "caption": f"📦 Бэкап базы данных\n🕐 {time.strftime('%Y-%m-%d %H:%M:%S')}"
                                })
                            
                            os.unlink(temp_db.name)
                        else:
                            with open(DB_PATH, 'rb') as f:
                                api("sendDocument", {
                                    "chat_id": uid,
                                    "document": f.read(),
                                    "caption": f"📦 Бэкап базы данных\n🕐 {time.strftime('%Y-%m-%d %H:%M:%S')}"
                                })
                    except Exception as e:
                        logger.error(f"GetDB error: {e}")
                        api("sendMessage", {"chat_id": uid, "text": "❌ Ошибка при создании бэкапа базы данных"})
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
                        })
                        
                        if copy_result.get('ok'):
                            stored_msg_id = copy_result['result']['message_id']
                            file_hash = secrets.token_urlsafe(6)
                            conn.execute("INSERT INTO files (hash, file_id, name, description, game, ts, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                         (file_hash, stored_msg_id, name, description, game, int(time.time()), uid))
                            conn.commit()
                            
                            file_link = f"https://t.me/plutoniumfilesBot?start={file_hash}"
                            api("sendMessage", {"chat_id": uid, "text": get_add_file_success(name, description, game, file_link), "parse_mode": "HTML"})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Ошибка сохранения файла"})
                    except Exception as e:
                        logger.error(f"Save error: {e}")
                        api("sendMessage", {"chat_id": uid, "text": f"❌ Ошибка: {e}"})
                    
                    waiting[uid] = None
                    continue
                
                # ОП - получение ID канала (ИСПРАВЛЕНО)
                elif waiting.get(uid) == "op_channel_id" and text:
                    try:
                        channel_id_str = text.strip()
                        channel_id = int(channel_id_str)
                        
                        logger.info(f"Проверка канала: {channel_id}")
                        
                        check_result = api("getChat", {"chat_id": channel_id})
                        
                        if not check_result.get('ok'):
                            api("sendMessage", {"chat_id": uid, "text": f"❌ Канал не найден!\n\nОшибка: {check_result.get('description', 'Неизвестная ошибка')}\n\n💡 Чтобы получить ID канала:\n1. Добавь бота @getmyid_bot в канал\n2. Напиши /start в канале\n3. Скопируй ID (начинается с -100)"})
                            waiting[uid] = None
                            continue
                        
                        link = get_channel_link(channel_id)
                        
                        if link:
                            conn.execute("UPDATE op_settings SET active = 0")
                            conn.execute("INSERT INTO op_settings (channel_id, target, current, active, link) VALUES (?, 0, 0, 1, ?)", 
                                        (channel_id, link))
                            conn.commit()
                            api("sendMessage", {"chat_id": uid, "text": get_op_success(channel_id, link), "parse_mode": "HTML"})
                            logger.info(f"ОП создана для канала {channel_id}")
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Не удалось получить ссылку на канал.\n\nУбедись, что канал публичный или у бота есть права администратора."})
                    except ValueError:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Отправь корректный ID канала!\n\nПример: -1001234567890\n\nID должен начинаться с -100"})
                    except Exception as e:
                        logger.error(f"OP creation error: {e}")
                        api("sendMessage", {"chat_id": uid, "text": f"❌ Ошибка: {str(e)}"})
                    
                    waiting[uid] = None
                    continue
                
                                # Реклама
                elif waiting.get(uid) == "ad_post" and (text or m.get('caption')):
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
                
                elif waiting.get(uid) == "ad_time" and text.isdigit():
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
                                    data = {"chat_id": user['user_id'], "text": msg_data['text']}
                                    if 'entities' in msg_data:
                                        data["entities"] = msg_data['entities']
                                    api("sendMessage", data)
                                elif 'caption' in msg_data:
                                    data = {
                                        "chat_id": user['user_id'],
                                        "photo": msg_data['photo'][-1]['file_id'],
                                        "caption": msg_data['caption']
                                    }
                                    if 'caption_entities' in msg_data:
                                        data["caption_entities"] = msg_data['caption_entities']
                                    api("sendPhoto", data)
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
                            waiting[uid] = "ban_action"
                            waiting[f"{uid}_target"] = target_id
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
                elif waiting.get(uid) == "broadcast" and (text or m.get('caption') or m.get('photo') or m.get('video') or m.get('document')):
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
                        elif 'video' in m:
                            preview = "🎥 Видео"
                        elif 'document' in m:
                            preview = "📄 Документ"
                        
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
                            logger.info(f"📦 Broadcasting: {msg_data.get('type')}")
                            
                            sent = send_broadcast(msg_data)
                            api("sendMessage", {"chat_id": uid, "text": get_broadcast_success(sent), "parse_mode": "HTML"})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Ошибка: нет сообщения"})
                    else:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Отменено"})
                    
                    if f"{uid}_broadcast" in waiting:
                        del waiting[f"{uid}_broadcast"]
                    del waiting[uid]
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
                
                # /start
                if text == "/start":
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
                        
                        new_cur = op['current'] + 1
                        conn.execute("UPDATE op_settings SET current = ? WHERE id = ?", (new_cur, op['id']))
                        if new_cur >= op['target']:
                            conn.execute("UPDATE op_settings SET active = 0 WHERE id = ?", (op['id'],))
                        conn.commit()
                    
                    api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": get_welcome_text(), "parse_mode": "HTML", "reply_markup": main_kb(uid)})
                
                # Ссылка на файл
                elif text.startswith("/start "):
                    f_hash = text.split(" ")[1]
                    
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

def yes_no_kb():
    return {
        "keyboard": [
            [{"text": "✅ ДА"}, {"text": "❌ НЕТ"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }

if __name__ == "__main__":
    main()
