import os, sqlite3, secrets, json, logging, urllib.request, time, threading

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8071432823:AAHh27N0UVMpt3grjhL0XX_XypAncrF8Mi8"
OWNER_ID = 1471307057
PHOTO_URL = "https://files.catbox.moe/jdtlab.jpg"
DB_PATH = "plutonium_full.db"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
conn.row_factory = sqlite3.Row

def init_db():
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, file_id TEXT, name TEXT, game TEXT, ts INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, downloads INTEGER DEFAULT 0, banned INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, perms TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS op_settings (id INTEGER PRIMARY KEY, link TEXT, target INTEGER, current INTEGER DEFAULT 0, active INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS ads (msg_id INTEGER PRIMARY KEY, chat_id INTEGER, expire INTEGER)")
    c.execute("INSERT OR IGNORE INTO admins (user_id, perms) VALUES (?, ?)", (OWNER_ID, '["all"]'))
    conn.commit()

init_db()

# --- СИСТЕМНЫЕ ФУНКЦИИ API ---
def api(method, data=None):
    try:
        req = urllib.request.Request(f"{API_URL}/{method}", data=json.dumps(data).encode() if data else None, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode())
    except: return {'ok': False}

def has_perm(uid, perm):
    if uid == OWNER_ID: return True
    row = conn.execute("SELECT perms FROM admins WHERE user_id = ?", (uid,)).fetchone()
    if not row: return False
    p = json.loads(row['perms'])
    return "all" in p or perm in p

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

# --- КЛАВИАТУРЫ (С ТГ ПРЕМ) ---
def main_kb(uid):
    kb = [[{"text": "Игры", "callback_data": "menu_games", "icon_custom_emoji_id": "5938413566624272793"}],
          [{"text": "Профиль", "callback_data": "menu_prof", "icon_custom_emoji_id": "6032693626394382504"},
           {"text": "Помощь", "callback_data": "menu_help", "icon_custom_emoji_id": "6030622631818956594"}]]
    if conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (uid,)).fetchone():
        kb.append([{"text": "Админ панель", "callback_data": "adm_root", "icon_custom_emoji_id": "6030445631921721471"}])
    return {"inline_keyboard": kb}

def admin_kb(uid):
    kb = [
        [{"text": "Рассылка", "callback_data": "a_broad", "icon_custom_emoji_id": "6037622221625626773"},
         {"text": "Очистка", "callback_data": "a_clean", "icon_custom_emoji_id": "6021792097454002931"}],
        [{"text": "ОП", "callback_data": "a_op", "icon_custom_emoji_id": "5962952497197748583"},
         {"text": "Статистика", "callback_data": "a_stat", "icon_custom_emoji_id": "6032742198179532882"}],
        [{"text": "Реклама", "callback_data": "a_ads", "icon_custom_emoji_id": "5904248647972820334"},
         {"text": "Бан/Разбан", "callback_data": "a_ban", "icon_custom_emoji_id": "5776227595708273495"}]
    ]
    if uid == OWNER_ID:
        kb.append([{"text": "Управление админами", "callback_data": "a_mng", "icon_custom_emoji_id": "6032636795387121097"}])
    kb.append([{"text": "🔙 Назад", "callback_data": "to_main"}])
    return {"inline_keyboard": kb}

# --- ОБРАБОТКА CALLBACK ---
waiting = {}

def handle_cb(cb):
    uid, cid, mid, data = cb['from']['id'], cb['message']['chat']['id'], cb['message']['message_id'], cb['data']
    u = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()

    if data == "to_main":
        cap = "<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет!**\n<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала @OfficialPlutonium**"
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": cap, "parse_mode": "HTML", "reply_markup": main_kb(uid)})

    elif data == "menu_prof":
        text = (f"<tg-emoji emoji-id=\"6032693626394382504\">👤</tg-emoji> **Профиль**\n"
                f"🆔 ID: <code>{uid}</code>\n📛 Имя: {u['first_name']}\n🔖 Username: @{u['username']}\n"
                f"📥 Файлов получено: {u['downloads']}")
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": text, "parse_mode": "HTML", 
                                   "reply_markup": {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "to_main"}]]}})

    elif data == "menu_games":
        kb = [[{"text": "Standoff 2", "callback_data": "g_so2", "icon_custom_emoji_id": "5393134637667094112"}],
              [{"text": "Pubg Mobile", "callback_data": "g_pubg", "icon_custom_emoji_id": "6073605466221451561"}],
              [{"text": "Other Games", "callback_data": "g_other", "icon_custom_emoji_id": "6095674537196653589"}],
              [{"text": "🔙 Назад", "callback_data": "to_main"}]]
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "🎮 **Выберите категорию:**", "reply_markup": {"inline_keyboard": kb}})

    elif data.startswith("g_"):
        game = data.split("_")[1]
        files = conn.execute("SELECT * FROM files WHERE game = ? ORDER BY ts DESC LIMIT 5", (game,)).fetchall()
        kb = [[{"text": f"📄 {f['name']}", "callback_data": f"dl_{f['hash']}"}] for f in files]
        kb.append([{"text": "🔙 Назад", "callback_data": "menu_games"}])
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": f"📂 Последние 5 файлов: {game.upper()}", "reply_markup": {"inline_keyboard": kb}})

    elif data.startswith("dl_"):
        f = conn.execute("SELECT * FROM files WHERE hash = ?", (data.split("_")[1],)).fetchone()
        cap = (f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> **Ваш Файл: {f['name']}**\n"
               f"<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> **Buy plutonium - @PlutoniumllcBot**")
        api("sendDocument", {"chat_id": cid, "document": f['file_id'], "caption": cap, "parse_mode": "HTML"})
        conn.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (uid,))
        conn.commit()

    elif data == "adm_root":
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ **Админ панель Plutonium**", "reply_markup": admin_kb(uid)})

    elif data == "a_stat":
        uc = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        dc = conn.execute("SELECT SUM(downloads) FROM users").fetchone()[0] or 0
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"👥 Юзеров: {uc}\n📥 Скачано: {dc}", "show_alert": True})

# --- ОСНОВНОЙ ЦИКЛ ---
def main():
    api("deleteWebhook", {"drop_pending_updates": True})
    offset = 0
    while True:
        try:
            upds = api("getUpdates", {"offset": offset, "timeout": 20})
            if not upds.get('ok'): continue
            for u in upds['result']:
                offset = u['update_id'] + 1
                if 'callback_query' in u: handle_cb(u['callback_query']); continue
                if 'message' not in u: continue
                
                m = u['message']
                uid, text = m['from']['id'], m.get('text', '')

                # Регистрация
                if not conn.execute("SELECT 1 FROM users WHERE user_id = ?", (uid,)).fetchone():
                    conn.execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)", 
                                 (uid, m['from'].get('username', 'None'), m['from'].get('first_name', 'User')))
                    conn.commit()
                    # Учет ОП
                    op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
                    if op:
                        new_cur = op['current'] + 1
                        conn.execute("UPDATE op_settings SET current = ? WHERE id = ?", (new_cur, op['id']))
                        if new_cur >= op['target']: conn.execute("UPDATE op_settings SET active = 0 WHERE id = ?", (op['id'],))
                        conn.commit()

                # Добавление файлов через хештеги
                if 'document' in m and has_perm(uid, "all"):
                    cap = m.get('caption', '').lower()
                    game = "other"
                    if "#standoff" in cap: game = "so2"
                    elif "#pubg" in cap: game = "pubg"
                    
                    f_hash = secrets.token_urlsafe(6)
                    f_name = m.get('caption', 'File').split('\n')[0][:25]
                    conn.execute("INSERT INTO files (hash, file_id, name, game, ts) VALUES (?, ?, ?, ?, ?)",
                                 (f_hash, m['document']['file_id'], f_name, game, int(time.time())))
                    conn.commit()
                    api("sendMessage", {"chat_id": uid, "text": f"✅ Файл добавлен в папку {game.upper()}"})

                if text == "/start":
                    op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
                    if op:
                        cap = "<tg-emoji emoji-id=\"6037249452824072506\">🔒</tg-emoji> **Подпишись для доступа!**"
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": cap, "parse_mode": "HTML", 
                                          "reply_markup": {"inline_keyboard": [[{"text": "✅ ПОДПИСАТЬСЯ", "url": op['link']}]]}})
                    else:
                        cap = "<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет!**\n<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала @OfficialPlutonium**"
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": cap, "parse_mode": "HTML", "reply_markup": main_kb(uid)})

            time.sleep(0.4)
        except Exception as e:
            logging.error(e)
            time.sleep(3)

if __name__ == "__main__": main()
    
