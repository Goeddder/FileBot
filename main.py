import os
import sqlite3
import secrets
import json
import logging
import urllib.request
import time
import re

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8071432823:AAHh27N0UVMpt3grjhL0XX_XypAncrF8Mi8"
OWNER_ID = 1471307057
CHANNEL_URL = "https://t.me/OfficialPlutonium"
CHANNEL_ID = "@OfficialPlutonium" # Добавлен @ для корректной работы API
DB_PATH = "files.db"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
conn.row_factory = sqlite3.Row

def init_db():
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            hash TEXT PRIMARY KEY,
            file_id TEXT,
            name TEXT,
            game TEXT,
            downloads INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_premium INTEGER DEFAULT 0,
            invited_by INTEGER DEFAULT 0,
            total_invites INTEGER DEFAULT 0,
            total_downloads INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
    conn.commit()

init_db()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return api("sendMessage", data)

def send_document(chat_id, file_id, caption=None):
    data = {"chat_id": chat_id, "document": file_id, "parse_mode": "HTML"}
    if caption:
        data["caption"] = caption
    return api("sendDocument", data)

def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return api("editMessageText", data)

def answer_callback(callback_id, text=None, show_alert=False):
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text
    if show_alert:
        data["show_alert"] = True
    return api("answerCallbackQuery", data)

def check_subscription(user_id):
    result = api("getChatMember", {"chat_id": CHANNEL_ID, "user_id": user_id})
    if result.get('ok'):
        status = result['result']['status']
        return status in ('member', 'administrator', 'creator')
    return False

def is_admin(user_id):
    return conn.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)).fetchone() is not None

def save_user(user_id, username, first_name, is_premium, inviter_id=None):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, is_premium, invited_by) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, first_name, 1 if is_premium else 0, inviter_id or 0)
    )
    if inviter_id and inviter_id != user_id:
        conn.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter_id,))
    conn.commit()

def get_user(user_id):
    return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

# --- КЛАВИАТУРЫ ---
def main_keyboard(is_p=False):
    if is_p:
        return {"keyboard": [[{"text": "📁 Игры"}], [{"text": "👋 Профиль"}, {"text": "🔗 Рефералка"}], [{"text": "❓ Помощь"}]], "resize_keyboard": True}
    return {"keyboard": [[{"text": "📁 Игры"}], [{"text": "👋 Профиль"}, {"text": "🔗 Рефералка"}], [{"text": "❓ Помощь"}]], "resize_keyboard": True}

def subscribe_keyboard(is_p=False):
    btn_text = "ПОДПИСАТЬСЯ" if is_p else "📢 ПОДПИСАТЬСЯ"
    check_text = "ПРОВЕРИТЬ" if is_p else "🔄 ПРОВЕРИТЬ"
    kb = [[{"text": btn_text, "url": CHANNEL_URL}], [{"text": check_text, "callback_data": "check_sub"}]]
    return {"inline_keyboard": kb}

def admin_keyboard(is_p=False):
    return {"keyboard": [[{"text": "📁 Добавить чит"}, {"text": "📋 Список читов"}], [{"text": "👥 Пользователи"}, {"text": "📢 Рассылка"}], [{"text": "📊 Статистика"}, {"text": "🔙 Главное меню"}]], "resize_keyboard": True}

# --- ОБРАБОТЧИКИ ---
waiting_for_file = {}
waiting_for_broadcast = {}

def process_callback(cb_id, chat_id, message_id, data, user_id):
    user_data = get_user(user_id)
    is_p = bool(user_data['is_premium']) if user_data else False
    
    if data == "check_sub":
        if check_subscription(user_id):
            first_name = user_data['first_name'] if user_data else 'Друг'
            if is_p:
                text = f"<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет, {first_name}!**\n\n<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала** @OfficialPlutonium"
            else:
                text = f"👋 **Привет, {first_name}!**\n\n🙂 **Я храню файлы с канала** @OfficialPlutonium"
            
            kb = admin_keyboard(is_p) if is_admin(user_id) else main_keyboard(is_p)
            answer_callback(cb_id, "✅ Доступ разрешен!")
            edit_message(chat_id, message_id, text, kb)
        else:
            answer_callback(cb_id, "❌ Вы не подписаны на канал!", True)
    
    elif data.startswith("file_"):
        file_hash = data.split("_")[1]
        f = conn.execute("SELECT * FROM files WHERE hash = ?", (file_hash,)).fetchone()
        if f:
            conn.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (file_hash,))
            conn.execute("UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            send_document(chat_id, f['file_id'], f"✅ <b>{f['name']}</b>")
            answer_callback(cb_id, "🚀 Файл отправлен")
        else:
            answer_callback(cb_id, "❌ Файл не найден", True)

def process_text(chat_id, user_id, text, is_p):
    if text == "👋 Профиль":
        u = get_user(user_id)
        if is_p:
            msg = f"<tg-emoji emoji-id=\"6032693626394382504\">👤</tg-emoji> **Профиль**\n\nID: `{user_id}`\nПриглашений: {u['total_invites']}\nСкачиваний: {u['total_downloads']}"
        else:
            msg = f"👤 **Профиль**\n\nID: `{user_id}`\nПриглашений: {u['total_invites']}\nСкачиваний: {u['total_downloads']}"
        send_message(chat_id, msg)
    
    elif text == "📁 Игры":
        games = conn.execute("SELECT DISTINCT game FROM files").fetchall()
        if not games:
            send_message(chat_id, "📭 Пока тут пусто")
            return
        btns = [[{"text": f"🎮 {g['game']}"}] for g in games]
        btns.append([{"text": "🔙 Главное меню"}])
        send_message(chat_id, "🎮 Выбери игру:", {"keyboard": btns, "resize_keyboard": True})

    elif text.startswith("🎮"):
        game_name = text.replace("🎮 ", "")
        files = conn.execute("SELECT * FROM files WHERE game = ?", (game_name,)).fetchall()
        kb = {"inline_keyboard": [[{"text": f"📄 {f['name']}", "callback_data": f"file_{f['hash']}"}] for f in files]}
        send_message(chat_id, f"Выбери чит для <b>{game_name}</b>:", kb)

    elif is_admin(user_id):
        if text == "📁 Добавить чит":
            waiting_for_file[user_id] = True
            send_message(chat_id, "Отправь файл с подписью: <code>Имя | Игра</code>")
        elif text == "📊 Статистика":
            u_cnt = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            f_cnt = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            send_message(chat_id, f"📊 Юзеров: {u_cnt}\n📁 Файлов: {f_cnt}")
        elif text == "🔙 Главное меню":
            send_message(chat_id, "Меню:", admin_keyboard(is_p))

# --- ГЛАВНЫЙ ЦИКЛ ---
def main():
    logger.info("🚀 Запуск Plutonium Bot...")
    offset = 0
    api("deleteWebhook", {"drop_pending_updates": True})
    
    while True:
        try:
            updates = api("getUpdates", {"offset": offset, "timeout": 30})
            if updates.get('ok') and updates.get('result'):
                for update in updates['result']:
                    offset = update['update_id'] + 1

                    # 1. ОБРАБОТКА КНОПОК (CALLBACK)
                    if 'callback_query' in update:
                        cb = update['callback_query']
                        process_callback(cb['id'], cb['message']['chat']['id'], cb['message']['message_id'], cb['data'], cb['from']['id'])
                        continue

                    # 2. ОБРАБОТКА СООБЩЕНИЙ
                    if 'message' in update:
                        msg = update['message']
                        chat_id = msg['chat']['id']
                        user_id = msg['from']['id']
                        is_p = msg['from'].get('is_premium', False)
                        
                        if not get_user(user_id):
                            save_user(user_id, msg['from'].get('username', ''), msg['from'].get('first_name', ''), is_p)

                        # Команда /start
                        if 'text' in msg and msg['text'].startswith('/start'):
                            if not check_subscription(user_id):
                                send_message(chat_id, "🔒 Подпишись на канал для доступа!", subscribe_keyboard(is_p))
                            else:
                                kb = admin_keyboard(is_p) if is_admin(user_id) else main_keyboard(is_p)
                                send_message(chat_id, "👋 Добро пожаловать!", kb)
                        
                        # Добавление файла (админ)
                        elif 'document' in msg and waiting_for_file.get(user_id):
                            waiting_for_file[user_id] = False
                            caption = msg.get('caption', 'Файл | Без игры')
                            name, game = [x.strip() for x in caption.split('|')] if '|' in caption else (caption, "Другое")
                            f_hash = secrets.token_urlsafe(8)
                            conn.execute("INSERT INTO files (hash, file_id, name, game) VALUES (?, ?, ?, ?)", (f_hash, msg['document']['file_id'], name, game))
                            conn.commit()
                            send_message(chat_id, f"✅ Добавлено: {name} ({game})")

                        elif 'text' in msg:
                            process_text(chat_id, user_id, msg['text'], is_p)

            time.sleep(0.2)
        except Exception as e:
            logger.error(f"Loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
            
