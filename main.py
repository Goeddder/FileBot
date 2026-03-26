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
CHANNEL_ID = "@OfficialPlutonium" # Обязательно с @ для публичных каналов
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

conn.execute("""
    CREATE TABLE IF NOT EXISTS files (
        hash TEXT PRIMARY KEY, file_id TEXT, name TEXT, game TEXT, downloads INTEGER DEFAULT 0
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, 
        is_premium INTEGER DEFAULT 0, invited_by INTEGER DEFAULT 0, 
        total_invites INTEGER DEFAULT 0, total_downloads INTEGER DEFAULT 0
    )
""")
conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
conn.commit()

# --- ВСПОМОГАТЕЛЬНЫЕ ---
def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup: data["reply_markup"] = json.dumps(reply_markup)
    return api("sendMessage", data)

def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup: data["reply_markup"] = json.dumps(reply_markup)
    return api("editMessageText", data)

def answer_callback(callback_id, text=None, show_alert=False):
    data = {"callback_query_id": callback_id}
    if text: data["text"] = text
    if show_alert: data["show_alert"] = True
    return api("answerCallbackQuery", data)

def check_subscription(user_id):
    res = api("getChatMember", {"chat_id": CHANNEL_ID, "user_id": user_id})
    if res.get('ok'):
        return res['result']['status'] in ('member', 'administrator', 'creator')
    return False

def is_admin(user_id):
    return conn.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)).fetchone() is not None

def get_user(user_id):
    return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

# --- КЛАВИАТУРЫ ---
def main_keyboard(is_p=False):
    key = "📁 Игры" if not is_p else "<tg-emoji emoji-id=\"5875008416132370818\">📁</tg-emoji> Игры"
    return {
        "keyboard": [[{"text": key}], [{"text": "👋 Профиль"}, {"text": "🔗 Рефералка"}], [{"text": "❓ Помощь"}]],
        "resize_keyboard": True
    }

def subscribe_keyboard(is_p=False):
    return {
        "inline_keyboard": [
            [{"text": "📢 ПОДПИСАТЬСЯ", "url": CHANNEL_URL}],
            [{"text": "🔄 ПРОВЕРИТЬ", "callback_data": "check_sub"}]
        ]
    }

def admin_keyboard(is_p=False):
    return {
        "keyboard": [[{"text": "📁 Добавить чит"}, {"text": "📋 Список читов"}], [{"text": "📊 Статистика"}, {"text": "🔙 Главное меню"}]],
        "resize_keyboard": True
    }

# --- ОБРАБОТЧИКИ ---
waiting_for_file = {}

def process_callback(cb_id, chat_id, message_id, data, user_id):
    u = get_user(user_id)
    is_p = bool(u['is_premium']) if u else False
    
    if data == "check_sub":
        if check_subscription(user_id):
            first_name = u['first_name'] if u else 'Пользователь'
            if is_p:
                text = f"<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет, {first_name}!**\n\n<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Доступ открыт!**"
            else:
                text = f"👋 **Привет, {first_name}!**\n\n🙂 **Доступ открыт! Используй меню ниже.**"
            
            kb = admin_keyboard(is_p) if is_admin(user_id) else main_keyboard(is_p)
            answer_callback(cb_id, "✅ Подписка подтверждена!")
            edit_message(chat_id, message_id, text, kb)
        else:
            answer_callback(cb_id, "❌ Вы всё еще не подписаны!", show_alert=True)
            
    elif data.startswith("file_"):
        f_hash = data.split("_")[1]
        f = conn.execute("SELECT * FROM files WHERE hash = ?", (f_hash,)).fetchone()
        if f:
            api("sendDocument", {"chat_id": chat_id, "document": f['file_id'], "caption": f"✅ {f['name']}"})
            answer_callback(cb_id, "🚀 Отправлено!")
        else:
            answer_callback(cb_id, "❌ Файл не найден", True)

def process_text(chat_id, user_id, text, is_p):
    if text == "👋 Профиль":
        u = get_user(user_id)
        msg = f"👤 **Профиль**\n\nID: `{user_id}`\nПриглашений: {u['total_invites']}\nСкачиваний: {u['total_downloads']}"
        send_message(chat_id, msg)
    
    elif text == "📁 Игры" or "Игры" in text:
        games = conn.execute("SELECT DISTINCT game FROM files").fetchall()
        if not games:
            send_message(chat_id, "📭 Пока читов нет.")
            return
        btns = [[{"text": f"🎮 {g['game']}"}] for g in games]
        btns.append([{"text": "🔙 Главное меню"}])
        send_message(chat_id, "🎮 Выбери игру:", {"keyboard": btns, "resize_keyboard": True})

    elif text.startswith("🎮"):
        g_name = text.replace("🎮 ", "")
        files = conn.execute("SELECT * FROM files WHERE game = ?", (g_name,)).fetchall()
        kb = {"inline_keyboard": [[{"text": f"📄 {f['name']}", "callback_data": f"file_{f['hash']}"}] for f in files]}
        send_message(chat_id, f"Читы для <b>{g_name}</b>:", kb)

    elif is_admin(user_id):
        if text == "📁 Добавить чит":
            waiting_for_file[user_id] = True
            send_message(chat_id, "Пришли файл с подписью: <code>Название | Игра</code>")
        elif text == "📊 Статистика":
            u_c = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            f_c = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            send_message(chat_id, f"📊 Юзеров: {u_c}\n📁 Файлов: {f_c}")
        elif text == "🔙 Главное меню":
            send_message(chat_id, "Главное меню:", admin_keyboard(is_p))

# --- MAIN ---
def main():
    logger.info("🚀 Запуск Plutonium Bot")
    # Исправляем 409 Conflict: удаляем вебхук
    api("deleteWebhook", {"drop_pending_updates": True})
    time.sleep(1)

    offset = 0
    while True:
        try:
            upd = api("getUpdates", {"offset": offset, "timeout": 20})
            if upd.get('ok') and upd.get('result'):
                for u in upd['result']:
                    offset = u['update_id'] + 1

                    if 'callback_query' in u:
                        cb = u['callback_query']
                        process_callback(cb['id'], cb['message']['chat']['id'], cb['message']['message_id'], cb['data'], cb['from']['id'])
                        continue

                    if 'message' in u:
                        m = u['message']
                        chat_id = m['chat']['id']
                        user_id = m['from']['id']
                        is_p = m['from'].get('is_premium', False)

                        # Регистрация
                        if not get_user(user_id):
                            conn.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, is_premium) VALUES (?, ?, ?, ?)", 
                                         (user_id, m['from'].get('username', ''), m['from'].get('first_name', ''), 1 if is_p else 0))
                            conn.commit()

                        if 'text' in m and m['text'].startswith('/start'):
                            if not check_subscription(user_id):
                                send_message(chat_id, "🔒 Подпишись на канал, чтобы пользоваться ботом!", subscribe_keyboard(is_p))
                            else:
                                kb = admin_keyboard(is_p) if is_admin(user_id) else main_keyboard(is_p)
                                send_message(chat_id, "👋 Привет! Ты уже подписан. Пользуйся!", kb)

                        elif 'document' in m and waiting_for_file.get(user_id):
                            waiting_for_file[user_id] = False
                            cap = m.get('caption', 'Файл | Без игры')
                            n, g = [x.strip() for x in cap.split('|')] if '|' in cap else (cap, "Прочее")
                            h = secrets.token_urlsafe(6)
                            conn.execute("INSERT INTO files (hash, file_id, name, game) VALUES (?, ?, ?, ?)", (h, m['document']['file_id'], n, g))
                            conn.commit()
                            send_message(chat_id, f"✅ Чит {n} добавлен!")

                        elif 'text' in m:
                            process_text(chat_id, user_id, m['text'], is_p)

            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
    
