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
PHOTO_URL = "https://files.catbox.moe/jdtlab.jpg"
DB_PATH = "files.db"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
conn.row_factory = sqlite3.Row

def init_db():
    conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, file_id TEXT, name TEXT, game TEXT, downloads INTEGER DEFAULT 0)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, 
            total_downloads INTEGER DEFAULT 0, invited_by INTEGER DEFAULT 0, 
            total_invites INTEGER DEFAULT 0
        )""")
    conn.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, role TEXT)")
    conn.execute("INSERT OR IGNORE INTO admins (user_id, role) VALUES (?, 'owner')", (OWNER_ID,))
    conn.commit()

init_db()

# --- API CORE ---
def api(method, data=None):
    url = f"{API_URL}/{method}"
    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                     headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        logger.error(f"API Error ({method}): {e}")
        return {'ok': False}

# --- ПРОВЕРКИ ---
def check_sub(uid):
    res = api("getChatMember", {"chat_id": CHANNEL_ID, "user_id": uid})
    return res.get('ok') and res['result']['status'] in ('member', 'administrator', 'creator')

def get_role(uid):
    row = conn.execute("SELECT role FROM admins WHERE user_id = ?", (uid,)).fetchone()
    return row['role'] if row else None

# --- ИНЛАЙН КНОПКИ С ICON_CUSTOM_EMOJI_ID ---
def main_kb(uid):
    kb = [
        [{"text": "Игры", "callback_data": "menu_games", "icon_custom_emoji_id": "5875008416132370818"}],
        [
            {"text": "Профиль", "callback_data": "menu_profile", "icon_custom_emoji_id": "6032693626394382504"},
            {"text": "Рефералка", "callback_data": "menu_ref", "icon_custom_emoji_id": "5438113593646132031"}
        ],
        [{"text": "Помощь", "callback_data": "menu_help", "icon_custom_emoji_id": "5431604010148701831"}]
    ]
    if get_role(uid):
        kb.append([{"text": "Админ-панель", "callback_data": "admin_main", "icon_custom_emoji_id": "5310169226856644648"}])
    return {"inline_keyboard": kb}

def sub_kb():
    return {"inline_keyboard": [
        [{"text": "ПОДПИСАТЬСЯ", "url": CHANNEL_URL, "icon_custom_emoji_id": "5927118708873892465"}],
        [{"text": "ПРОВЕРИТЬ", "callback_data": "check_sub", "icon_custom_emoji_id": "5774022692642492953"}]
    ]}

def admin_kb():
    return {"inline_keyboard": [
        [{"text": "Рассылка", "callback_data": "adm_broadcast", "icon_custom_emoji_id": "5310076249404621168"}],
        [{"text": "Очистка", "callback_data": "adm_clean", "icon_custom_emoji_id": "5431604010148701831"}],
        [{"text": "Назад", "callback_data": "back_main", "icon_custom_emoji_id": "5285032475490273112"}]
    ]}

# --- ОБРАБОТЧИКИ ---
waiting_action = {}

def handle_callback(cb):
    uid, cid, mid, data = cb['from']['id'], cb['message']['chat']['id'], cb['message']['message_id'], cb['data']
    u = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()

    if data == "check_sub":
        if check_sub(uid):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "✅ Доступ разрешен!"})
            text = (
                "<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет!**\n"
                "<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала** @OfficialPlutonium\n"
                "👇 **Используй кнопки ниже для навигации**"
            )
            api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": text, "parse_mode": "HTML", "reply_markup": main_kb(uid)})
        else:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "❌ Вы не подписаны!", "show_alert": True})

    elif data == "menu_profile":
        text = (
            f"<tg-emoji emoji-id=\"6032693626394382504\">👤</tg-emoji> **Профиль**\n"
            f"<tg-emoji emoji-id=\"5886505193180239900\">🆔</tg-emoji> ID: <code>{uid}</code>\n"
            f"<tg-emoji emoji-id=\"5879770735999717115\">📛</tg-emoji> Имя: {u['first_name']}\n"
            f"<tg-emoji emoji-id=\"5814247475141153332\">🔖</tg-emoji> Username: @{u['username']}\n"
            f"<tg-emoji emoji-id=\"6039802767931871481\">📥</tg-emoji> Файлов получено: {u['total_downloads']}"
        )
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": text, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": [[{"text": "Назад", "callback_data": "back_main", "icon_custom_emoji_id": "5285032475490273112"}]]}})

    elif data == "admin_main" and get_role(uid):
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ **Админ-панель Plutonium**", "parse_mode": "HTML", "reply_markup": admin_kb()})

    elif data == "adm_broadcast" and get_role(uid):
        waiting_action[uid] = "broadcast"
        api("sendMessage", {"chat_id": cid, "text": "📝 **Введите текст для рассылки всем пользователям:**"})

    elif data == "back_main":
        text = "👋 Привет!\n🙂 Я храню файлы с канала @OfficialPlutonium\n👇 Используй кнопки ниже"
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": text, "parse_mode": "HTML", "reply_markup": main_kb(uid)})

# --- ЦИКЛ ---
def main():
    api("deleteWebhook", {"drop_pending_updates": True})
    offset = 0
    while True:
        try:
            upd = api("getUpdates", {"offset": offset, "timeout": 20})
            if not upd.get('ok'): continue
            for u in upd['result']:
                offset = u['update_id'] + 1
                if 'callback_query' in u:
                    handle_callback(u['callback_query'])
                    continue
                if 'message' not in u: continue
                
                m = u['message']
                uid, text = m['from']['id'], m.get('text', '')

                # Регистрация
                if not conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone():
                    inviter = 0
                    if text.startswith('/start ref_'):
                        try: inviter = int(text.split('_')[1])
                        except: pass
                    conn.execute("INSERT INTO users (user_id, username, first_name, invited_by) VALUES (?, ?, ?, ?)", (uid, m['from'].get('username', 'none'), m['from'].get('first_name', 'User'), inviter))
                    if inviter != 0:
                        conn.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter,))
                    conn.commit()

                # Рассылка
                if uid in waiting_action and waiting_action[uid] == "broadcast":
                    del waiting_action[uid]
                    all_users = conn.execute("SELECT user_id FROM users").fetchall()
                    sent = 0
                    for row in all_users:
                        if api("sendMessage", {"chat_id": row['user_id'], "text": text}).get('ok'): sent += 1
                    api("sendMessage", {"chat_id": uid, "text": f"✅ Рассылка завершена! Получили: {sent} чел."})
                    continue

                if text.startswith('/start'):
                    if not check_sub(uid):
                        cap = (f"<tg-emoji emoji-id=\"6037249452824072506\">🔒</tg-emoji> **Привет, {m['from'].get('first_name')}!**\n"
                               f"<tg-emoji emoji-id=\"6039630677182254664\">🔓</tg-emoji> **Подпишись на канал для доступа.**")
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": cap, "parse_mode": "HTML", "reply_markup": sub_kb()})
                    else:
                        cap = "👋 **Привет!**\n🙂 Я храню файлы с канала @OfficialPlutonium\n👇 Используй кнопки ниже"
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": cap, "parse_mode": "HTML", "reply_markup": main_kb(uid)})

            time.sleep(0.5)
        except: time.sleep(5)

if __name__ == "__main__": main()
    
