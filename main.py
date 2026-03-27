import os
import sqlite3
import secrets
import json
import logging
import urllib.request
import time
import threading
import re

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8071432823:AAHh27N0UVMpt3grjhL0XX_XypAncrF8Mi8"
OWNER_ID = 1471307057
PHOTO_URL = "https://files.catbox.moe/jdtlab.jpg"
DB_PATH = "plutonium_full.db"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ID каналов
CHANNEL_ID = -1003607014773
STORAGE_CHANNEL_ID = -1003677537552

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
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
        logger.error(f"API error: {e}")
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
        return None
    except:
        return None

# --- КЛАВИАТУРЫ ---
def main_kb(uid):
    kb = [
        [{"text": "Игры", "callback_data": "menu_games", "icon_custom_emoji_id": "5938413566624272793"}],
        [{"text": "Профиль", "callback_data": "menu_prof", "icon_custom_emoji_id": "6032693626394382504"},
         {"text": "Помощь", "callback_data": "menu_help", "icon_custom_emoji_id": "6030622631818956594"}]
    ]
    if is_admin(uid):
        kb.append([{"text": "Админ панель", "callback_data": "adm_root", "icon_custom_emoji_id": "6030445631921721471"}])
    return {"inline_keyboard": kb}

def admin_kb(uid):
    kb = [
        [{"text": "Рассылка", "callback_data": "a_broad", "icon_custom_emoji_id": "6037622221625626773"},
         {"text": "Очистка", "callback_data": "a_clean", "icon_custom_emoji_id": "6021792097454002931"}],
        [{"text": "Добавить файл", "callback_data": "a_addfile", "icon_custom_emoji_id": "5805648413743651862"},
         {"text": "ОП", "callback_data": "a_op", "icon_custom_emoji_id": "5962952497197748583"}],
        [{"text": "Реклама", "callback_data": "a_ads", "icon_custom_emoji_id": "5904248647972820334"},
         {"text": "Бан/Разбан", "callback_data": "a_ban", "icon_custom_emoji_id": "5776227595708273495"}],
        [{"text": "Статистика", "callback_data": "a_stat", "icon_custom_emoji_id": "6032742198179532882"}]
    ]
    if uid == OWNER_ID:
        kb.append([{"text": "Управление админами", "callback_data": "a_mng", "icon_custom_emoji_id": "6032636795387121097"}])
    kb.append([{"text": "Назад", "callback_data": "to_main"}])
    return {"inline_keyboard": kb}

def games_kb():
    return {
        "inline_keyboard": [
            [{"text": "Standoff 2", "callback_data": "game_so2", "icon_custom_emoji_id": "5393134637667094112"}],
            [{"text": "Pubg Mobile", "callback_data": "game_pubg", "icon_custom_emoji_id": "6073605466221451561"}],
            [{"text": "Other Games", "callback_data": "game_other", "icon_custom_emoji_id": "6095674537196653589"}],
            [{"text": "Назад", "callback_data": "to_main"}]
        ]
    }

def files_kb(files):
    kb = []
    for f in files[:10]:
        kb.append([{"text": f"📄 {f['name'][:30]}", "callback_data": f"dl_{f['hash']}"}])
    kb.append([{"text": "Назад", "callback_data": "menu_games"}])
    return {"inline_keyboard": kb}

def back_kb():
    return {"inline_keyboard": [[{"text": "Назад", "callback_data": "to_main"}]]}

def perms_kb(target_id):
    return {
        "inline_keyboard": [
            [{"text": "Добавить файл", "callback_data": f"perm_addfile_{target_id}", "icon_custom_emoji_id": "5805648413743651862"}],
            [{"text": "Рассылка", "callback_data": f"perm_broad_{target_id}", "icon_custom_emoji_id": "6037622221625626773"}],
            [{"text": "Все права", "callback_data": f"perm_all_{target_id}", "icon_custom_emoji_id": "6030445631921721471"}],
            [{"text": "Отмена", "callback_data": "a_mng"}]
        ]
    }

def op_check_kb(channel_id):
    link = get_channel_link(channel_id)
    if link:
        return {
            "inline_keyboard": [
                [{"text": "ПОДПИСАТЬСЯ", "url": link, "icon_custom_emoji_id": "5927118708873892465"}],
                [{"text": "ПРОВЕРИТЬ", "callback_data": f"op_check_{channel_id}", "icon_custom_emoji_id": "5774022692642492953"}]
            ]
        }
    return None

def channel_check_kb():
    return {
        "inline_keyboard": [
            [{"text": "ПОДПИСАТЬСЯ", "url": "https://t.me/OfficialPlutonium", "icon_custom_emoji_id": "5927118708873892465"}],
            [{"text": "ПРОВЕРИТЬ", "callback_data": "channel_check", "icon_custom_emoji_id": "5774022692642492953"}]
        ]
    }

def ban_kb(target_id):
    return {
        "inline_keyboard": [
            [{"text": "🔒 ЗАБАНИТЬ", "callback_data": f"ban_do_{target_id}", "icon_custom_emoji_id": "6030563507299160824"}],
            [{"text": "🔓 РАЗБАНИТЬ", "callback_data": f"unban_do_{target_id}", "icon_custom_emoji_id": "6028205772117118673"}],
            [{"text": "❌ Отмена", "callback_data": "a_ban", "icon_custom_emoji_id": "5774022692642492953"}]
        ]
    }

def file_footer_kb():
    return {
        "inline_keyboard": [
            [{"text": "Plutonium", "url": "https://t.me/OfficialPlutonium", "icon_custom_emoji_id": "5339472242529045815"}]
        ]
    }

# --- ТЕКСТЫ С TG PREMIUM ЭМОДЗИ ---
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
            f"<tg-emoji emoji-id=\"6039573425268201570\">📥</tg-emoji> Скачиваний: 0\n\n"
            f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> При выдаче файла будет:\n"
            f"<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> Buy plutonium - @PlutoniumllcBot")

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
    return ("<tg-emoji emoji-id=\"6039422865189638057\">📢</tg-emoji> Размещение рекламы\n\n"
            "<tg-emoji emoji-id=\"5904248647972820334\">🤝</tg-emoji> Отправь пост для рекламы.\n\n"
            "<tg-emoji emoji-id=\"6028338546736107668\">😂</tg-emoji> Поддерживается TG Premium эмодзи.")

def get_ad_time_prompt():
    return ("<tg-emoji emoji-id=\"6039454987250044861\">⏱️</tg-emoji> Введи время в часах (от 1 до 72):\n\nПример: 24")

def get_ad_success(sent, hours):
    return (f"<tg-emoji emoji-id=\"5938252440926163756\">✅</tg-emoji> Реклама отправлена {sent} пользователям\n\n"
            f"<tg-emoji emoji-id=\"5891100675042974129\">🦈</tg-emoji> Удаление через {hours} часов")

def get_op_prompt():
    return ("<tg-emoji emoji-id=\"6028171274939797252\">🔗</tg-emoji> Создание ОП\n\n"
            "<tg-emoji emoji-id=\"5895364284782743985\">🦍</tg-emoji> Введи ID канала для обязательной подписки.\n\n"
            "<tg-emoji emoji-id=\"5769289093221454192\">🇺🇸</tg-emoji> Пример: -1001234567890")

def get_op_success(channel_id, link):
    return (f"<tg-emoji emoji-id=\"5938252440926163756\">✅</tg-emoji> ОП создана!\n\n"
            f"<tg-emoji emoji-id=\"5776424837786374634\">⭐</tg-emoji> Канал ID: {channel_id}\n"
            f"<tg-emoji emoji-id=\"6028171274939797252\">🔥</tg-emoji> Ссылка: {link}")

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

# --- ХРАНИЛИЩА ---
waiting = {}
processed_hashes = set()

# --- ФУНКЦИЯ ОТПРАВКИ С ЭНТИТИС ---
def send_with_entities(chat_id, message_data):
    try:
        if 'text' in message_data:
            data = {
                "chat_id": chat_id,
                "text": message_data['text'],
                "parse_mode": "HTML"
            }
            if 'entities' in message_data:
                data["entities"] = message_data['entities']
            return api("sendMessage", data)
        elif 'caption' in message_data:
            data = {
                "chat_id": chat_id,
                "photo": message_data['photo'][-1]['file_id'],
                "caption": message_data['caption'],
                "parse_mode": "HTML"
            }
            if 'caption_entities' in message_data:
                data["caption_entities"] = message_data['caption_entities']
            return api("sendPhoto", data)
    except Exception as e:
        logger.error(f"Send with entities error: {e}")
        return None

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
    logger.info(f"📢 Канал подписки ID: {CHANNEL_ID}")
    logger.info(f"💾 Канал хранения ID: {STORAGE_CHANNEL_ID}")
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
                
                # ОП - получение ID канала
                elif waiting.get(uid) == "op_channel_id" and text:
                    try:
                        channel_id = int(text.strip())
                        link = get_channel_link(channel_id)
                        if link:
                            conn.execute("UPDATE op_settings SET active = 0")
                            conn.execute("INSERT INTO op_settings (channel_id, target, current, active, link) VALUES (?, 0, 0, 1, ?)", 
                                        (channel_id, link))
                            conn.commit()
                            api("sendMessage", {"chat_id": uid, "text": get_op_success(channel_id, link), "parse_mode": "HTML"})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Не удалось получить ссылку на канал"})
                    except:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Отправь корректный ID канала!\n\nПример: -1001234567890"})
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
                                send_with_entities(user['user_id'], msg_data)
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
                elif waiting.get(uid) == "broadcast" and text:
                    if text == "/cancel":
                        waiting[uid] = None
                        api("sendMessage", {"chat_id": uid, "text": "✅ Рассылка отменена"})
                        continue
                    
                    msg_data = {
                        'text': text
                    }
                    if 'entities' in m:
                        msg_data['entities'] = m['entities']
                    
                    users = conn.execute("SELECT user_id FROM users WHERE banned = 0").fetchall()
                    sent = 0
                    for user in users:
                        try:
                            send_with_entities(user['user_id'], msg_data)
                            sent += 1
                        except:
                            pass
                        time.sleep(0.05)
                    api("sendMessage", {"chat_id": uid, "text": get_broadcast_success(sent), "parse_mode": "HTML"})
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
                    
                    f = conn.execute("SELECT * FROM files WHERE hash = ?", (f_hash,)).fetchone()
                    if f:
                        api("sendMessage", {"chat_id": uid, "text": "<tg-emoji emoji-id=\"6037373985400819577\">📤</tg-emoji> Отправляю файл!", "parse_mode": "HTML"})
                        
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
                    
                    time.sleep(5)
                    processed_hashes.discard(f_hash)
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
