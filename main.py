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
    c.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, file_id INTEGER, name TEXT, game TEXT, ts INTEGER, created_by INTEGER, downloads INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, downloads INTEGER DEFAULT 0, banned INTEGER DEFAULT 0, last_active INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, perms TEXT, added_by INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS op_settings (id INTEGER PRIMARY KEY, channel_id INTEGER, target INTEGER, current INTEGER DEFAULT 0, active INTEGER DEFAULT 0, link TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS ads (msg_id INTEGER PRIMARY KEY, chat_id INTEGER, expire INTEGER)")
    c.execute("INSERT OR IGNORE INTO admins (user_id, perms, added_by) VALUES (?, ?, ?)", (OWNER_ID, '["all"]', OWNER_ID))
    conn.commit()

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

# --- КЛАВИАТУРЫ (с TG Premium эмодзи) ---
def main_kb(uid):
    kb = [
        [{"text": "<tg-emoji emoji-id=\"5938413566624272793\">🎮</tg-emoji> Игры", "callback_data": "menu_games", "parse_mode": "HTML"}],
        [{"text": "<tg-emoji emoji-id=\"6032693626394382504\">👤</tg-emoji> Профиль", "callback_data": "menu_prof", "parse_mode": "HTML"},
         {"text": "<tg-emoji emoji-id=\"6030622631818956594\">❓</tg-emoji> Помощь", "callback_data": "menu_help", "parse_mode": "HTML"}]
    ]
    if is_admin(uid):
        kb.append([{"text": "<tg-emoji emoji-id=\"6030445631921721471\">⚡</tg-emoji> Админ панель", "callback_data": "adm_root", "parse_mode": "HTML"}])
    return {"inline_keyboard": kb}

def admin_kb(uid):
    kb = [
        [{"text": "<tg-emoji emoji-id=\"6037622221625626773\">📢</tg-emoji> Рассылка", "callback_data": "a_broad", "parse_mode": "HTML"},
         {"text": "<tg-emoji emoji-id=\"6021792097454002931\">🧹</tg-emoji> Очистка", "callback_data": "a_clean", "parse_mode": "HTML"}],
        [{"text": "<tg-emoji emoji-id=\"5805648413743651862\">📁</tg-emoji> Добавить файл", "callback_data": "a_addfile", "parse_mode": "HTML"},
         {"text": "<tg-emoji emoji-id=\"5962952497197748583\">🔗</tg-emoji> ОП", "callback_data": "a_op", "parse_mode": "HTML"}],
        [{"text": "<tg-emoji emoji-id=\"5904248647972820334\">📢</tg-emoji> Реклама", "callback_data": "a_ads", "parse_mode": "HTML"},
         {"text": "<tg-emoji emoji-id=\"5776227595708273495\">🚫</tg-emoji> Бан/Разбан", "callback_data": "a_ban", "parse_mode": "HTML"}],
        [{"text": "<tg-emoji emoji-id=\"6032742198179532882\">📊</tg-emoji> Статистика", "callback_data": "a_stat", "parse_mode": "HTML"}]
    ]
    if uid == OWNER_ID:
        kb.append([{"text": "<tg-emoji emoji-id=\"6032636795387121097\">👑</tg-emoji> Управление админами", "callback_data": "a_mng", "parse_mode": "HTML"}])
    kb.append([{"text": "🔙 Назад", "callback_data": "to_main"}])
    return {"inline_keyboard": kb}

def games_kb():
    return {
        "inline_keyboard": [
            [{"text": "<tg-emoji emoji-id=\"5393134637667094112\">🎮</tg-emoji> Standoff 2", "callback_data": "game_so2", "parse_mode": "HTML"}],
            [{"text": "<tg-emoji emoji-id=\"6073605466221451561\">🎮</tg-emoji> Pubg Mobile", "callback_data": "game_pubg", "parse_mode": "HTML"}],
            [{"text": "<tg-emoji emoji-id=\"6095674537196653589\">🎮</tg-emoji> Other Games", "callback_data": "game_other", "parse_mode": "HTML"}],
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
            [{"text": "<tg-emoji emoji-id=\"5805648413743651862\">📁</tg-emoji> Добавить файл", "callback_data": f"perm_addfile_{target_id}", "parse_mode": "HTML"}],
            [{"text": "<tg-emoji emoji-id=\"6037622221625626773\">📢</tg-emoji> Рассылка", "callback_data": f"perm_broad_{target_id}", "parse_mode": "HTML"}],
            [{"text": "<tg-emoji emoji-id=\"6030445631921721471\">👑</tg-emoji> Все права", "callback_data": f"perm_all_{target_id}", "parse_mode": "HTML"}],
            [{"text": "❌ Отмена", "callback_data": "a_mng"}]
        ]
    }

def op_check_kb(channel_id):
    link = get_channel_link(channel_id)
    if link:
        return {
            "inline_keyboard": [
                [{"text": "<tg-emoji emoji-id=\"5927118708873892465\">✅</tg-emoji> ПОДПИСАТЬСЯ", "url": link, "parse_mode": "HTML"}],
                [{"text": "<tg-emoji emoji-id=\"5774022692642492953\">🔄</tg-emoji> ПРОВЕРИТЬ", "callback_data": f"op_check_{channel_id}", "parse_mode": "HTML"}]
            ]
        }
    return None

def channel_check_kb():
    return {
        "inline_keyboard": [
            [{"text": "<tg-emoji emoji-id=\"5927118708873892465\">✅</tg-emoji> ПОДПИСАТЬСЯ", "url": "https://t.me/OfficialPlutonium", "parse_mode": "HTML"}],
            [{"text": "<tg-emoji emoji-id=\"5774022692642492953\">🔄</tg-emoji> ПРОВЕРИТЬ", "callback_data": "channel_check", "parse_mode": "HTML"}]
        ]
    }

# --- ХРАНИЛИЩА ---
waiting = {}

# --- ТЕКСТЫ С TG PREMIUM ЭМОДЗИ ---
def get_welcome_text():
    return "<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> Привет!\n<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> Я храню файлы с канала @OfficialPlutonium\n👇 Используй кнопки ниже для навигации"

def get_subscribe_text():
    return "<tg-emoji emoji-id=\"6037249452824072506\">🔒</tg-emoji> Привет!\n<tg-emoji emoji-id=\"6039630677182254664\">🔓</tg-emoji> Подпишись на канал @OfficialPlutonium для доступа!"

def get_op_text():
    return "<tg-emoji emoji-id=\"6037249452824072506\">🔒</tg-emoji> Привет!\n<tg-emoji emoji-id=\"6039630677182254664\">🔓</tg-emoji> Подпишись для доступа!"

def get_profile_text(uid, first_name, username, downloads):
    return (f"<tg-emoji emoji-id=\"6032693626394382504\">👤</tg-emoji> Профиль\n\n"
            f"<tg-emoji emoji-id=\"5886505193180239900\">🆔</tg-emoji> ID: <code>{uid}</code>\n"
            f"<tg-emoji emoji-id=\"5879770735999717115\">📛</tg-emoji> Имя: {first_name}\n"
            f"<tg-emoji emoji-id=\"5814247475141153332\">🔖</tg-emoji> Username: @{username}\n"
            f"<tg-emoji emoji-id=\"6039802767931871481\">📥</tg-emoji> Файлов получено: {downloads}")

def get_file_footer(name):
    return f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> Ваш Файл: {name}\n<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> Buy plutonium - @PlutoniumllcBot"

def get_add_file_success(name, game, file_link):
    return (f"✅ Файл добавлен!\n\n"
            f"📄 Название: {name}\n"
            f"🎮 Игра: {game.upper()}\n"
            f"🔗 Ссылка: {file_link}\n"
            f"📥 Скачиваний: 0\n\n"
            f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> При выдаче файла будет:\n"
            f"<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> Buy plutonium - @PlutoniumllcBot")

# --- ОБРАБОТКА CALLBACK ---
def handle_cb(cb):
    uid = cb['from']['id']
    cid = cb['message']['chat']['id']
    mid = cb['message']['message_id']
    data = cb['data']
    
    u = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()
    
    # Проверка подписки на канал
    if data == "channel_check":
        if check_subscription(uid, CHANNEL_ID):
            api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": get_welcome_text(), "parse_mode": "HTML", "reply_markup": main_kb(uid)})
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
                api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": get_welcome_text(), "parse_mode": "HTML", "reply_markup": main_kb(uid)})
            else:
                api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Вы еще не подписались!", "show_alert": True})
        except:
            pass
        return
    
    if data == "to_main":
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": get_welcome_text(), "parse_mode": "HTML", "reply_markup": main_kb(uid)})
    
    elif data == "menu_prof":
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": get_profile_text(uid, u['first_name'], u['username'], u['downloads']), "parse_mode": "HTML", "reply_markup": back_kb()})
    
    elif data == "menu_help":
        text = "❓ Помощь\n\n1️⃣ Нажми Игры\n2️⃣ Выбери игру\n3️⃣ Нажми на название чита\n4️⃣ Файл автоматически отправится\n\n📌 Для админов есть дополнительные функции."
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": text, "parse_mode": "HTML", "reply_markup": back_kb()})
    
    elif data == "menu_games":
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "🎮 Выберите игру:", "reply_markup": games_kb()})
    
    elif data.startswith("game_"):
        game_map = {"so2": "standoff", "pubg": "pubg", "other": "other"}
        game_code = data.split("_")[1]
        game_name = game_map.get(game_code, "other")
        
        files = conn.execute("SELECT * FROM files WHERE game = ? ORDER BY ts DESC LIMIT 10", (game_name,)).fetchall()
        if files:
            cap = f"🎮 {game_name.upper()}\n\n📂 Последние файлы:"
            api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": cap, "reply_markup": files_kb(files)})
        else:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет файлов", "show_alert": True})
    
    elif data.startswith("dl_"):
        f_hash = data.split("_")[1]
        f = conn.execute("SELECT * FROM files WHERE hash = ?", (f_hash,)).fetchone()
        if f:
            cap = get_file_footer(f['name'])
            api("copyMessage", {
                "chat_id": cid,
                "from_chat_id": STORAGE_CHANNEL_ID,
                "message_id": f['file_id'],
                "caption": cap,
                "parse_mode": "HTML"
            })
            conn.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (uid,))
            conn.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (f_hash,))
            conn.commit()
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"✅ {f['name']} отправлен!"})
    
    elif data == "adm_root":
        if not is_admin(uid):
            return
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ Админ панель Plutonium", "reply_markup": admin_kb(uid)})
    
    elif data == "a_stat":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        uc = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        dc = conn.execute("SELECT SUM(downloads) FROM users").fetchone()[0] or 0
        fc = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"👥 Юзеров: {uc}\n📥 Скачано: {dc}\n📁 Файлов: {fc}", "show_alert": True})
    
    elif data == "a_clean":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        now = int(time.time())
        deleted = conn.execute("DELETE FROM users WHERE last_active < ? AND user_id NOT IN (SELECT user_id FROM admins)", (now - 30*24*3600,)).rowcount
        conn.commit()
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"Удалено неактивных: {deleted}", "show_alert": True})
    
    elif data == "a_addfile":
        if not has_perm(uid, "addfile") and not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "addfile"
        api("sendMessage", {"chat_id": cid, "text": "📤 Отправь файл\n\nВ подписи укажи:\nНазвание | #игра\n\nПример: Aimbot | #standoff\n\nДоступные игры:\n#standoff - Standoff 2\n#pubg - Pubg Mobile\n#other - Other Games"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь файл"})
    
    elif data == "a_op":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "op_channel_id"
        api("sendMessage", {"chat_id": cid, "text": "🔗 Создание ОП\n\nВведи ID канала для обязательной подписки.\n\nПример: -1001234567890"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Введи ID канала"})
    
    elif data == "a_ads":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "ad_post"
        api("sendMessage", {"chat_id": cid, "text": "📢 Размещение рекламы\n\nОтправь пост для рекламы.\n\nПоддерживается TG Premium эмодзи."})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь пост"})
    
    elif data == "a_ban":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "ban_user"
        api("sendMessage", {"chat_id": cid, "text": "🚫 Бан/Разбан пользователя\n\nОтправь ID или username.\n\nПример: 1471307057 или @username"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь ID или username"})
    
    elif data == "a_broad":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "broadcast"
        api("sendMessage", {"chat_id": cid, "text": "📢 Рассылка\n\nОтправь сообщение для рассылки.\n\nПоддерживается TG Premium эмодзи.\n\n/cancel - отмена"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь сообщение"})
    
    elif data == "a_mng":
        if uid != OWNER_ID:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Только для владельца", "show_alert": True})
            return
        waiting[uid] = "add_admin"
        api("sendMessage", {"chat_id": cid, "text": "👑 Управление админами\n\nОтправь ID или username.\n\nПример: 1471307057 или @username"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь ID или username"})
    
    elif data.startswith("perm_"):
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
    
    elif data.startswith("ban_do_"):
        target_id = int(data.split("_")[2])
        conn.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        api("sendMessage", {"chat_id": cid, "text": f"✅ Пользователь {target_id} забанен"})
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ Админ панель Plutonium", "reply_markup": admin_kb(uid)})
    
    elif data.startswith("ban_do_"):
        target_id = int(data.split("_")[2])
        conn.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        api("sendMessage", {"chat_id": cid, "text": f"✅ Пользователь {target_id} забанен"})
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ Админ панель Plutonium", "reply_markup": admin_kb(uid)})
    
    elif data.startswith("unban_do_"):
        target_id = int(data.split("_")[2])
        conn.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        api("sendMessage", {"chat_id": cid, "text": f"✅ Пользователь {target_id} разбанен"})
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ Админ панель Plutonium", "reply_markup": admin_kb(uid)})

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
                    
                    name = cap.split('\n')[0][:50] if cap else "File"
                    if '|' in name:
                        name = name.split('|')[0].strip()
                    
                    try:
                        copy_result = api("copyMessage", {
                            "chat_id": STORAGE_CHANNEL_ID,
                            "from_chat_id": chat_id,
                            "message_id": m['message_id']
                        })
                        
                        if copy_result.get('ok'):
                            stored_msg_id = copy_result['result']['message_id']
                            file_hash = secrets.token_urlsafe(6)
                            conn.execute("INSERT INTO files (hash, file_id, name, game, ts, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                                         (file_hash, stored_msg_id, name, game, int(time.time()), uid))
                            conn.commit()
                            
                            file_link = f"https://t.me/plutoniumfilesBot?start={file_hash}"
                            api("sendMessage", {"chat_id": uid, "text": get_add_file_success(name, game, file_link), "parse_mode": "HTML"})
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
                            api("sendMessage", {"chat_id": uid, "text": f"✅ ОП создана!\n\nКанал ID: {channel_id}\nСсылка: {link}"})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Не удалось получить ссылку на канал"})
                    except:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Отправь корректный ID канала!\n\nПример: -1001234567890"})
                    waiting[uid] = None
                    continue
                
                # Реклама
                elif waiting.get(uid) == "ad_post" and (text or m.get('caption')):
                    waiting[uid] = "ad_time"
                    waiting[f"{uid}_msg"] = json.dumps(m)
                    api("sendMessage", {"chat_id": uid, "text": "⏱️ Введи время в часах (от 1 до 72):\n\nПример: 24"})
                    continue
                
                elif waiting.get(uid) == "ad_time" and text.isdigit():
                    hours = int(text)
                    if 1 <= hours <= 72:
                        expire = int(time.time()) + hours * 3600
                        msg_data = json.loads(waiting.get(f"{uid}_msg", "{}"))
                        
                        if 'message_id' in msg_data:
                            conn.execute("INSERT INTO ads (msg_id, chat_id, expire) VALUES (?, ?, ?)", 
                                        (msg_data['message_id'], chat_id, expire))
                            conn.commit()
                        
                        users = conn.execute("SELECT user_id FROM users WHERE banned = 0").fetchall()
                        sent = 0
                        for user in users:
                            try:
                                if 'text' in msg_data:
                                    api("sendMessage", {"chat_id": user['user_id'], "text": msg_data['text'], "parse_mode": "HTML"})
                                elif 'caption' in msg_data:
                                    photo_id = msg_data.get('photo', [{}])[-1].get('file_id', '')
                                    if photo_id:
                                        api("sendPhoto", {"chat_id": user['user_id'], "photo": photo_id, "caption": msg_data['caption'], "parse_mode": "HTML"})
                                sent += 1
                            except:
                                pass
                            time.sleep(0.05)
                        
                        api("sendMessage", {"chat_id": uid, "text": f"✅ Реклама отправлена {sent} пользователям\n\nУдаление через {hours} часов"})
                        waiting[uid] = None
                        if f"{uid}_msg" in waiting:
                            del waiting[f"{uid}_msg"]
                    else:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Введи число от 1 до 72"})
                    continue
                
                # Бан/Разбан - первый шаг
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
                                               "reply_markup": {"inline_keyboard": [
                                                   [{"text": "🔒 ЗАБАНИТЬ", "callback_data": f"ban_do_{target_id}"}],
                                                   [{"text": "🔓 РАЗБАНИТЬ", "callback_data": f"unban_do_{target_id}"}],
                                                   [{"text": "❌ Отмена", "callback_data": "a_ban"}]
                                               ]}})
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
                    
                    users = conn.execute("SELECT user_id FROM users WHERE banned = 0").fetchall()
                    sent = 0
                    for user in users:
                        try:
                            api("sendMessage", {"chat_id": user['user_id'], "text": text, "parse_mode": "HTML"})
                            sent += 1
                        except:
                            pass
                        time.sleep(0.05)
                    api("sendMessage", {"chat_id": uid, "text": f"✅ Рассылка завершена!\n\nОтправлено: {sent} пользователям"})
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
                    # Проверка подписки на канал
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
                        
                        new_cur = op['current'] + 1
                        conn.execute("UPDATE op_settings SET current = ? WHERE id = ?", (new_cur, op['id']))
                        if new_cur >= op['target']:
                            conn.execute("UPDATE op_settings SET active = 0 WHERE id = ?", (op['id'],))
                        conn.commit()
                    
                    api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": get_welcome_text(), "parse_mode": "HTML", "reply_markup": main_kb(uid)})
                
                # Ссылка на файл
                elif text.startswith("/start "):
                    f_hash = text.split(" ")[1]
                    f = conn.execute("SELECT * FROM files WHERE hash = ?", (f_hash,)).fetchone()
                    if f:
                        cap = get_file_footer(f['name'])
                        api("copyMessage", {
                            "chat_id": uid,
                            "from_chat_id": STORAGE_CHANNEL_ID,
                            "message_id": f['file_id'],
                            "caption": cap,
                            "parse_mode": "HTML"
                        })
                        conn.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (uid,))
                        conn.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (f_hash,))
                        conn.commit()
                    else:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Файл не найден"})
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
