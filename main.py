import os
import sqlite3
import secrets
import json
import logging
import urllib.request
import time
import threading

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8071432823:AAHh27N0UVMpt3grjhL0XX_XypAncrF8Mi8"
OWNER_ID = 1471307057
PHOTO_URL = "https://files.catbox.moe/jdtlab.jpg"
DB_PATH = "plutonium_final.db"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)

# --- ИНИЦИАЛИЗАЦИЯ БД ---
conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
conn.row_factory = sqlite3.Row

def init_db():
    c = conn.cursor()
    # Файлы и игры
    c.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, hash TEXT, file_id TEXT, name TEXT, game TEXT, timestamp INTEGER)")
    # Юзеры и баны
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, downloads INTEGER DEFAULT 0, banned INTEGER DEFAULT 0, last_seen INTEGER)")
    # Админы и права (JSON список: ["add_file", "broadcast", "op", "ads", "manage_admins"])
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, permissions TEXT)")
    # Обязательная подписка (ОП)
    c.execute("CREATE TABLE IF NOT EXISTS op_settings (id INTEGER PRIMARY KEY, link TEXT, target INTEGER, current INTEGER, active INTEGER DEFAULT 0)")
    # Реклама (посты с удалением по времени)
    c.execute("CREATE TABLE IF NOT EXISTS ads (msg_id INTEGER PRIMARY KEY, chat_id INTEGER, delete_at INTEGER)")
    
    c.execute("INSERT OR IGNORE INTO admins (user_id, permissions) VALUES (?, ?)", (OWNER_ID, '["all"]'))
    conn.commit()

init_db()

# --- API CORE ---
def api(method, data=None):
    try:
        req = urllib.request.Request(f"{API_URL}/{method}", 
                                     data=json.dumps(data).encode() if data else None, 
                                     headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        logging.error(f"API Error {method}: {e}")
        return {'ok': False}

def has_perm(uid, perm):
    if uid == OWNER_ID: return True
    row = conn.execute("SELECT permissions FROM admins WHERE user_id = ?", (uid,)).fetchone()
    if not row: return False
    p = json.loads(row['permissions'])
    return "all" in p or perm in p

# --- КЛАВИАТУРЫ ---
def main_kb(uid):
    kb = [[{"text": "Игры", "callback_data": "g_root", "icon_custom_emoji_id": "5938413566624272793"}],
          [{"text": "Профиль", "callback_data": "u_prof", "icon_custom_emoji_id": "6032693626394382504"},
           {"text": "Помощь", "callback_data": "u_help", "icon_custom_emoji_id": "6030622631818956594"}]]
    if conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (uid,)).fetchone():
        kb.append([{"text": "Админ панель", "callback_data": "a_menu", "icon_custom_emoji_id": "6030445631921721471"}])
    return {"inline_keyboard": kb}

def admin_kb(uid):
    kb = [
        [{"text": "Рассылка", "callback_data": "a_broad", "icon_custom_emoji_id": "6037622221625626773"},
         {"text": "Очистка", "callback_data": "a_clean", "icon_custom_emoji_id": "6021792097454002931"}],
        [{"text": "Добавить файл", "callback_data": "a_addf", "icon_custom_emoji_id": "5805648413743651862"},
         {"text": "ОП", "callback_data": "a_op", "icon_custom_emoji_id": "5962952497197748583"}],
        [{"text": "Реклама", "callback_data": "a_ads", "icon_custom_emoji_id": "5904248647972820334"},
         {"text": "Бан/Разбан", "callback_data": "a_ban", "icon_custom_emoji_id": "5776227595708273495"}],
        [{"text": "Статистика", "callback_data": "a_stats", "icon_custom_emoji_id": "6032742198179532882"}]
    ]
    if uid == OWNER_ID:
        kb.append([{"text": "Управление админами", "callback_data": "a_mng", "icon_custom_emoji_id": "6032636795387121097"}])
    kb.append([{"text": "🔙 Назад", "callback_data": "back_main"}])
    return {"inline_keyboard": kb}

# --- ЛОГИКА ОЧИСТКИ И РЕКЛАМЫ (ФОН) ---
def cleaner_thread():
    while True:
        now = int(time.time())
        # Удаление старой рекламы
        expired = conn.execute("SELECT * FROM ads WHERE delete_at < ?", (now,)).fetchall()
        for ad in expired:
            api("deleteMessage", {"chat_id": ad['chat_id'], "message_id": ad['msg_id']})
            conn.execute("DELETE FROM ads WHERE msg_id = ?", (ad['msg_id'],))
        conn.commit()
        time.sleep(60)

threading.Thread(target=cleaner_thread, daemon=True).start()

# --- ОБРАБОТЧИКИ ---
wait = {} # Состояния ожидания ввода

def handle_cb(cb):
    uid, cid, mid, data = cb['from']['id'], cb['message']['chat']['id'], cb['message']['message_id'], cb['data']
    
    if data == "back_main":
        cap = "<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет!**\n<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала @OfficialPlutonium**\n👇 **Используй кнопки ниже**"
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": cap, "parse_mode": "HTML", "reply_markup": main_kb(uid)})

    elif data == "a_menu" and conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (uid,)).fetchone():
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ **Админ-панель**", "reply_markup": admin_kb(uid)})

    elif data == "g_root":
        kb = [[{"text": "Standoff 2", "callback_data": "g_so2", "icon_custom_emoji_id": "5393134637667094112"}],
              [{"text": "Pubg Mobile", "callback_data": "g_pubg", "icon_custom_emoji_id": "6073605466221451561"}],
              [{"text": "Other Games", "callback_data": "g_other", "icon_custom_emoji_id": "6095674537196653589"}],
              [{"text": "🔙 Назад", "callback_data": "back_main"}]]
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "🎮 **Выберите категорию:**", "reply_markup": {"inline_keyboard": kb}})

    elif data.startswith("g_"):
        game = data.split("_")[1]
        files = conn.execute("SELECT * FROM files WHERE game = ? ORDER BY timestamp DESC LIMIT 5", (game,)).fetchall()
        kb = [[{"text": f"📄 {f['name']}", "callback_data": f"file_dl_{f['hash']}"}] for f in files]
        kb.append([{"text": "🔙 Назад", "callback_data": "g_root"}])
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": f"📂 Последние файлы категории: **{game.upper()}**", "reply_markup": {"inline_keyboard": kb}})

    elif data.startswith("file_dl_"):
        f = conn.execute("SELECT * FROM files WHERE hash = ?", (data.split("_")[2],)).fetchone()
        cap = f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> **Ваш Файл: {f['name']}**\n<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> **Buy plutonium - @PlutoniumllcBot**"
        api("sendDocument", {"chat_id": cid, "document": f['file_id'], "caption": cap, "parse_mode": "HTML"})
        conn.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (uid,))
        conn.commit()

    elif data == "a_clean" and has_perm(uid, "all"):
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "🧹 Начинаю глубокую очистку..."})
        users = conn.execute("SELECT user_id FROM users").fetchall()
        deleted = 0
        for u_row in users:
            res = api("getChat", {"chat_id": u_row['user_id']})
            if not res.get('ok'):
                conn.execute("DELETE FROM users WHERE user_id = ?", (u_row['user_id'],))
                deleted += 1
        conn.commit()
        api("sendMessage", {"chat_id": cid, "text": f"✅ Очистка завершена. Удалено: {deleted} пользователей."})

    elif data == "a_stats":
        u_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        f_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        d_count = conn.execute("SELECT SUM(downloads) FROM users").fetchone()[0] or 0
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"📊 Юзеров: {u_count}\n📁 Файлов: {f_count}\n📥 Скачиваний: {d_count}", "show_alert": True})

# --- ГЛАВНЫЙ ЦИКЛ ---
def main():
    api("deleteWebhook", {"drop_pending_updates": True})
    offset = 0
    while True:
        try:
            upd = api("getUpdates", {"offset": offset, "timeout": 20})
            if not upd.get('ok'): continue
            for u in upd['result']:
                offset = u['update_id'] + 1
                if 'callback_query' in u: handle_cb(u['callback_query']); continue
                if 'message' not in u: continue
                
                m = u['message']
                uid, text = m['from']['id'], m.get('text', '')
                
                # Регистрация / Обновление визита
                if not conn.execute("SELECT 1 FROM users WHERE user_id = ?", (uid,)).fetchone():
                    conn.execute("INSERT INTO users (user_id, username, first_name, last_seen) VALUES (?, ?, ?, ?)", 
                                 (uid, m['from'].get('username', 'None'), m['from'].get('first_name', 'User'), int(time.time())))
                    conn.commit()
                    # Счетчик ОП
                    op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
                    if op:
                        conn.execute("UPDATE op_settings SET current = current + 1 WHERE id = ?", (op['id'],))
                        if op['current'] + 1 >= op['target']:
                            conn.execute("UPDATE op_settings SET active = 0 WHERE id = ?", (op['id'],))
                        conn.commit()
                else:
                    conn.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (int(time.time()), uid))
                    conn.commit()

                # Парсинг файлов по хештегам
                if 'document' in m and has_perm(uid, "add_file"):
                    cap = m.get('caption', '').lower()
                    game = "other"
                    if "#standoff" in cap: game = "so2"
                    elif "#pubg" in cap: game = "pubg"
                    
                    f_hash = secrets.token_urlsafe(6)
                    f_name = m.get('caption', 'Файл').split('\n')[0][:30]
                    conn.execute("INSERT INTO files (hash, file_id, name, game, timestamp) VALUES (?, ?, ?, ?, ?)",
                                 (f_hash, m['document']['file_id'], f_name, game, int(time.time())))
                    conn.commit()
                    api("sendMessage", {"chat_id": uid, "text": f"✅ Файл добавлен в {game.upper()}"})

                if text == "/start":
                    op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
                    if op:
                        cap = "<tg-emoji emoji-id=\"6037249452824072506\">🔒</tg-emoji> **Для доступа подпишитесь:**"
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": cap, "parse_mode": "HTML", 
                                          "reply_markup": {"inline_keyboard": [[{"text": "Подписаться", "url": op['link']}]]}})
                    else:
                        cap = "<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет!**\n<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала @OfficialPlutonium**"
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": cap, "parse_mode": "HTML", "reply_markup": main_kb(uid)})

            time.sleep(0.4)
        except Exception as e:
            logging.error(e)
            time.sleep(3)

if __name__ == "__main__":
    main()
    
