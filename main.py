import os
import sqlite3
import secrets
import json
import logging
import urllib.request
import time

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8071432823:AAHh27N0UVMpt3grjhL0XX_XypAncrF8Mi8"
OWNER_ID = 1471307057
CHANNEL_URL = "https://t.me/OfficialPlutonium"
CHANNEL_ID = "@OfficialPlutonium"
DB_PATH = "files.db"
PHOTO_URL = "https://files.catbox.moe/jdtlab.jpg"
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
conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, file_id TEXT, name TEXT, game TEXT, downloads INTEGER DEFAULT 0)")
conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, total_downloads INTEGER DEFAULT 0)")
conn.commit()

# --- ВСПОМОГАТЕЛЬНЫЕ ---
def send_photo(chat_id, caption, reply_markup=None):
    data = {"chat_id": chat_id, "photo": PHOTO_URL, "caption": caption, "parse_mode": "HTML"}
    if reply_markup: data["reply_markup"] = json.dumps(reply_markup)
    return api("sendPhoto", data)

def edit_caption(chat_id, message_id, caption, reply_markup=None):
    data = {"chat_id": chat_id, "message_id": message_id, "caption": caption, "parse_mode": "HTML"}
    if reply_markup: data["reply_markup"] = json.dumps(reply_markup)
    return api("editMessageCaption", data)

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

# --- КЛАВИАТУРЫ (ИНЛАЙН) ---
def main_inline_kb():
    return {
        "inline_keyboard": [
            [{"text": "📁 Игры", "callback_data": "menu_games"}],
            [{"text": "👤 Профиль", "callback_data": "menu_profile"}],
            [{"text": "❓ Помощь", "callback_data": "menu_help"}]
        ]
    }

def subscribe_inline_kb():
    return {
        "inline_keyboard": [
            [{"text": "ПОДПИСАТЬСЯ", "url": CHANNEL_URL}],
            [{"text": "ПРОВЕРИТЬ", "callback_data": "check_sub"}]
        ]
    }

# --- ОБРАБОТЧИКИ ---
def process_callback(cb_id, chat_id, message_id, data, user_id):
    u = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    
    if data == "check_sub":
        if check_subscription(user_id):
            answer_callback(cb_id, "✅ Доступ открыт!")
            text = (
                "<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет!**\n"
                "<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала** @OfficialPlutonium\n"
                "<tg-emoji emoji-id=\"5875008416132370818\">📁</tg-emoji> **Используй кнопки ниже для навигации**"
            )
            edit_caption(chat_id, message_id, text, main_inline_kb())
        else:
            answer_callback(cb_id, "❌ Вы не подписаны!", True)

    elif data == "menu_profile":
        text = (
            f"<tg-emoji emoji-id=\"6032693626394382504\">👤</tg-emoji> **Профиль**\n"
            f"<tg-emoji emoji-id=\"5886505193180239900\">🆔</tg-emoji> ID: `{user_id}`\n"
            f"<tg-emoji emoji-id=\"5879770735999717115\">📛</tg-emoji> Имя: {u['first_name']}\n"
            f"<tg-emoji emoji-id=\"5814247475141153332\">🔖</tg-emoji> Username: @{u['username']}\n"
            f"<tg-emoji emoji-id=\"6039802767931871481\">📥</tg-emoji> Файлов получено: {u['total_downloads']}"
        )
        edit_caption(chat_id, message_id, text, {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "back_main"}]]})

    elif data == "back_main":
        text = "👋 Привет!\n🙂 Я храню файлы с канала @OfficialPlutonium\n👇 Используй кнопки ниже"
        edit_caption(chat_id, message_id, text, main_inline_kb())

    elif data.startswith("file_"):
        f_hash = data.split("_")[1]
        f = conn.execute("SELECT * FROM files WHERE hash = ?", (f_hash,)).fetchone()
        if f:
            conn.execute("UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            caption = (
                f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> **Ваш Файл: {f['name']}**\n"
                f"<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> **Buy plutonium - @PlutoniumllcBot**"
            )
            api("sendDocument", {"chat_id": chat_id, "document": f['file_id'], "caption": caption, "parse_mode": "HTML"})
            answer_callback(cb_id, "✅ Файл отправлен!")

# --- MAIN ---
def main():
    api("deleteWebhook", {"drop_pending_updates": True})
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
                        user_id = m['from']['id']
                        name = m['from'].get('first_name', 'User')
                        uname = m['from'].get('username', 'none')

                        conn.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)", (user_id, uname, name))
                        conn.commit()

                        if 'text' in m and m['text'].startswith('/start'):
                            if not check_subscription(user_id):
                                cap = (
                                    f"<tg-emoji emoji-id=\"6037249452824072506\">🔒</tg-emoji> **Привет, {name}!**\n"
                                    f"<tg-emoji emoji-id=\"6039630677182254664\">🔓</tg-emoji> **Подпишись на канал для доступа к читам.**"
                                )
                                send_photo(m['chat']['id'], cap, subscribe_inline_kb())
                            else:
                                cap = "👋 Привет!\n🙂 Я храню файлы с канала @OfficialPlutonium\n👇 Используй кнопки ниже"
                                send_photo(m['chat']['id'], cap, main_inline_kb())
            time.sleep(0.5)
        except: time.sleep(5)

if __name__ == "__main__":
    main()
