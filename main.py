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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
conn.row_factory = sqlite3.Row

def init_db():
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, file_id TEXT, name TEXT, game TEXT, ts INTEGER, created_by INTEGER, downloads INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, downloads INTEGER DEFAULT 0, banned INTEGER DEFAULT 0, last_active INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, perms TEXT, added_by INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS op_settings (id INTEGER PRIMARY KEY, link TEXT, target INTEGER, current INTEGER DEFAULT 0, active INTEGER DEFAULT 0)")
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

# --- КЛАВИАТУРЫ (С ТГ ПРЕМ) ---
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
    kb.append([{"text": "🔙 Назад", "callback_data": "to_main"}])
    return {"inline_keyboard": kb}

def games_kb():
    return {
        "inline_keyboard": [
            [{"text": "Standoff 2", "callback_data": "game_so2", "icon_custom_emoji_id": "5393134637667094112"}],
            [{"text": "Pubg Mobile", "callback_data": "game_pubg", "icon_custom_emoji_id": "6073605466221451561"}],
            [{"text": "Other Games", "callback_data": "game_other", "icon_custom_emoji_id": "6095674537196653589"}],
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

# --- ХРАНИЛИЩА ДЛЯ ОЖИДАНИЙ ---
waiting = {}

# --- ОБРАБОТКА CALLBACK ---
def handle_cb(cb):
    uid = cb['from']['id']
    cid = cb['message']['chat']['id']
    mid = cb['message']['message_id']
    data = cb['data']
    
    u = conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()
    
    # Главное меню
    if data == "to_main":
        cap = ("<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет!**\n"
               "<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала @OfficialPlutonium**\n"
               "👇 **Используй кнопки ниже для навигации**")
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": cap, "parse_mode": "HTML", "reply_markup": main_kb(uid)})
    
    # Профиль
    elif data == "menu_prof":
        text = (f"<tg-emoji emoji-id=\"6032693626394382504\">👤</tg-emoji> **Профиль**\n\n"
                f"<tg-emoji emoji-id=\"5886505193180239900\">🆔</tg-emoji> ID: <code>{uid}</code>\n"
                f"<tg-emoji emoji-id=\"5879770735999717115\">📛</tg-emoji> Имя: {u['first_name']}\n"
                f"<tg-emoji emoji-id=\"5814247475141153332\">🔖</tg-emoji> Username: @{u['username']}\n"
                f"<tg-emoji emoji-id=\"6039802767931871481\">📥</tg-emoji> Файлов получено: {u['downloads']}")
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": text, "parse_mode": "HTML", "reply_markup": back_kb()})
    
    # Помощь
    elif data == "menu_help":
        text = ("❓ **Помощь**\n\n"
                "1️⃣ Нажми «Игры»\n"
                "2️⃣ Выбери игру\n"
                "3️⃣ Нажми на название чита\n"
                "4️⃣ Файл автоматически отправится\n\n"
                "📌 Для админов есть дополнительные функции.")
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": text, "parse_mode": "HTML", "reply_markup": back_kb()})
    
    # Игры
    elif data == "menu_games":
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "🎮 **Выберите игру:**", "reply_markup": games_kb()})
    
    # Выбор игры
    elif data.startswith("game_"):
        game_map = {"so2": "standoff", "pubg": "pubg", "other": "other"}
        game_code = data.split("_")[1]
        game_name = game_map.get(game_code, "other")
        
        files = conn.execute("SELECT * FROM files WHERE game = ? ORDER BY ts DESC LIMIT 10", (game_name,)).fetchall()
        if files:
            cap = f"🎮 **{game_name.upper()}**\n\n📂 Последние файлы:"
            api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": cap, "reply_markup": files_kb(files)})
        else:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет файлов в этой категории", "show_alert": True})
    
    # Скачивание файла
    elif data.startswith("dl_"):
        f_hash = data.split("_")[1]
        f = conn.execute("SELECT * FROM files WHERE hash = ?", (f_hash,)).fetchone()
        if f:
            cap = (f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> **Ваш Файл: {f['name']}**\n"
                   f"<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> **Buy plutonium - @PlutoniumllcBot**")
            api("sendDocument", {"chat_id": cid, "document": f['file_id'], "caption": cap, "parse_mode": "HTML"})
            conn.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (uid,))
            conn.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (f_hash,))
            conn.commit()
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"✅ {f['name']} отправлен!"})
    
    # Админ панель
    elif data == "adm_root":
        if not is_admin(uid):
            return
        api("editMessageCaption", {"chat_id": cid, "message_id": mid, "caption": "⚡ **Админ панель Plutonium**", "reply_markup": admin_kb(uid)})
    
    # Статистика
    elif data == "a_stat":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        uc = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        dc = conn.execute("SELECT SUM(downloads) FROM users").fetchone()[0] or 0
        fc = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"👥 Юзеров: {uc}\n📥 Скачано: {dc}\n📁 Файлов: {fc}", "show_alert": True})
    
    # Очистка неактивных
    elif data == "a_clean":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        now = int(time.time())
        deleted = conn.execute("DELETE FROM users WHERE last_active < ? AND user_id NOT IN (SELECT user_id FROM admins)", (now - 30*24*3600,)).rowcount
        conn.commit()
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": f"Удалено неактивных: {deleted}", "show_alert": True})
    
    # Добавить файл
    elif data == "a_addfile":
        if not has_perm(uid, "addfile") and not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "addfile"
        api("sendMessage", {"chat_id": cid, "text": "📤 **Отправь файл**\n\nВ подписи укажи:\n`Название | #игра`\n\nПример: `Aimbot | #standoff`\n\nДоступные игры:\n#standoff - Standoff 2\n#pubg - Pubg Mobile\n#other - Other Games"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь файл с подписью"})
    
    # ОП (обязательная подписка)
    elif data == "a_op":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "op_link"
        api("sendMessage", {"chat_id": cid, "text": "🔗 **Создание ОП**\n\nОтправь ссылку на канал/пост для обязательной подписки.\n\nПример: `https://t.me/OfficialPlutonium`"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь ссылку"})
    
    # Реклама
    elif data == "a_ads":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "ad_post"
        api("sendMessage", {"chat_id": cid, "text": "📢 **Размещение рекламы**\n\nОтправь пост (сообщение) для рекламы.\n\nПоддерживается форматирование и TG Premium эмодзи."})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь пост"})
    
    # Бан/Разбан
    elif data == "a_ban":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "ban_user"
        api("sendMessage", {"chat_id": cid, "text": "🚫 **Бан/Разбан пользователя**\n\nОтправь ID или username пользователя.\n\nПример: `1471307057` или `@username`"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь ID или username"})
    
    # Рассылка
    elif data == "a_broad":
        if not has_perm(uid, "all"):
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Нет прав", "show_alert": True})
            return
        waiting[uid] = "broadcast"
        api("sendMessage", {"chat_id": cid, "text": "📢 **Рассылка**\n\nОтправь сообщение для рассылки всем пользователям.\n\nПоддерживается форматирование и TG Premium эмодзи.\n\n/cancel - отмена"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь сообщение"})
    
    # Управление админами
    elif data == "a_mng":
        if uid != OWNER_ID:
            api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Только для владельца", "show_alert": True})
            return
        waiting[uid] = "add_admin"
        api("sendMessage", {"chat_id": cid, "text": "👑 **Управление админами**\n\nОтправь ID или username пользователя для управления правами.\n\nПример: `1471307057` или `@username`"})
        api("answerCallbackQuery", {"callback_query_id": cb['id'], "text": "Отправь ID или username"})

# --- ОСНОВНОЙ ЦИКЛ ---
def main():
    logger.info("🚀 Запуск Plutonium Bot")
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
                
                # Callback
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
                
                # Регистрация нового пользователя
                if not conn.execute("SELECT 1 FROM users WHERE user_id = ?", (uid,)).fetchone():
                    conn.execute("INSERT INTO users (user_id, username, first_name, last_active) VALUES (?, ?, ?, ?)", 
                                 (uid, username, first_name, int(time.time())))
                    conn.commit()
                    
                    # Проверка ОП (обязательная подписка)
                    op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
                    if op:
                        new_cur = op['current'] + 1
                        conn.execute("UPDATE op_settings SET current = ? WHERE id = ?", (new_cur, op['id']))
                        if new_cur >= op['target']:
                            conn.execute("UPDATE op_settings SET active = 0 WHERE id = ?", (op['id'],))
                        conn.commit()
                
                # Обновляем активность
                conn.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (int(time.time()), uid))
                conn.commit()
                
                # Обработка ожиданий
                if waiting.get(uid) == "addfile" and 'document' in m:
                    cap = m.get('caption', '')
                    game = "other"
                    if "#standoff" in cap.lower():
                        game = "standoff"
                    elif "#pubg" in cap.lower():
                        game = "pubg"
                    elif "#other" in cap.lower():
                        game = "other"
                    
                    # Парсим название
                    name = cap.split('\n')[0][:50] if cap else "File"
                    if '|' in name:
                        name = name.split('|')[0].strip()
                    
                    f_hash = secrets.token_urlsafe(6)
                    conn.execute("INSERT INTO files (hash, file_id, name, game, ts, created_by) VALUES (?, ?, ?, ?, ?, ?)",
                                 (f_hash, m['document']['file_id'], name, game, int(time.time()), uid))
                    conn.commit()
                    
                    # Отправляем ссылку на файл
                    file_link = f"https://t.me/{m['chat']['username'] or 'PlutoniumCheatsBot'}?start={f_hash}"
                    cap = (f"✅ **Файл добавлен!**\n\n"
                           f"📄 **Название:** {name}\n"
                           f"🎮 **Игра:** {game.upper()}\n"
                           f"🔗 **Ссылка:** `{file_link}`\n"
                           f"📥 **Скачиваний:** 0\n\n"
                           f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> При выдаче файла будет:\n"
                           f"<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> Buy plutonium - @PlutoniumllcBot")
                    api("sendMessage", {"chat_id": uid, "text": cap, "parse_mode": "HTML"})
                    waiting[uid] = None
                    continue
                
                # ОП - получение ссылки
                elif waiting.get(uid) == "op_link" and text:
                    link = text.strip()
                    if link.startswith("http"):
                        waiting[uid] = "op_target"
                        waiting[f"{uid}_link"] = link
                        api("sendMessage", {"chat_id": uid, "text": "🔢 Введи количество пользователей для ОП:\n\nПример: `100`"})
                    else:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Отправь корректную ссылку!"})
                    continue
                
                elif waiting.get(uid) == "op_target" and text.isdigit():
                    target = int(text)
                    link = waiting.get(f"{uid}_link", "")
                    conn.execute("INSERT INTO op_settings (link, target, current, active) VALUES (?, ?, 0, 1)", (link, target))
                    conn.commit()
                    api("sendMessage", {"chat_id": uid, "text": f"✅ ОП создана!\n\nСсылка: {link}\nЦель: {target} пользователей"})
                    waiting[uid] = None
                    if f"{uid}_link" in waiting:
                        del waiting[f"{uid}_link"]
                    continue
                
                # Реклама - получение поста
                elif waiting.get(uid) == "ad_post" and (text or m.get('caption')):
                    msg_text = text or m.get('caption', '')
                    waiting[uid] = "ad_time"
                    waiting[f"{uid}_msg"] = json.dumps(m)
                    api("sendMessage", {"chat_id": uid, "text": "⏱️ Введи время в часах (от 1 до 72):\n\nПример: `24`"})
                    continue
                
                elif waiting.get(uid) == "ad_time" and text.isdigit():
                    hours = int(text)
                    if 1 <= hours <= 72:
                        expire = int(time.time()) + hours * 3600
                        msg_data = json.loads(waiting.get(f"{uid}_msg", "{}"))
                        
                        # Отправляем рекламу всем пользователям
                        users = conn.execute("SELECT user_id FROM users").fetchall()
                        sent = 0
                        for user in users:
                            try:
                                if 'text' in msg_data:
                                    api("sendMessage", {"chat_id": user['user_id'], "text": msg_data['text'], "parse_mode": "HTML"})
                                elif 'caption' in msg_data:
                                    api("sendPhoto", {"chat_id": user['user_id'], "photo": msg_data.get('photo', [{}])[-1].get('file_id', ''), "caption": msg_data['caption'], "parse_mode": "HTML"})
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
                
                # Бан/Разбан
                elif waiting.get(uid) == "ban_user" and text:
                    target = text.strip().replace('@', '')
                    try:
                        target_id = int(target) if target.isdigit() else None
                        if not target_id:
                            user = conn.execute("SELECT user_id FROM users WHERE username = ?", (target,)).fetchone()
                            target_id = user['user_id'] if user else None
                        
                        if target_id:
                            user = conn.execute("SELECT * FROM users WHERE user_id = ?", (target_id,)).fetchone()
                            if user and user['banned']:
                                conn.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (target_id,))
                                api("sendMessage", {"chat_id": uid, "text": f"✅ Пользователь {target_id} разбанен"})
                            elif user:
                                conn.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (target_id,))
                                api("sendMessage", {"chat_id": uid, "text": f"✅ Пользователь {target_id} забанен"})
                            else:
                                api("sendMessage", {"chat_id": uid, "text": "❌ Пользователь не найден"})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Пользователь не найден"})
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
                                # Клавиатура для выбора прав
                                perms_kb = {
                                    "inline_keyboard": [
                                        [{"text": "📁 Добавить файл", "callback_data": f"perm_addfile_{target_id}"}],
                                        [{"text": "📢 Рассылка", "callback_data": f"perm_broad_{target_id}"}],
                                        [{"text": "👑 Все права", "callback_data": f"perm_all_{target_id}"}],
                                        [{"text": "🔙 Отмена", "callback_data": "a_mng"}]
                                    ]
                                }
                                api("sendMessage", {"chat_id": uid, "text": f"👑 Выбери права для {target_id}:", "reply_markup": perms_kb})
                        else:
                            api("sendMessage", {"chat_id": uid, "text": "❌ Пользователь не найден"})
                    except:
                        api("sendMessage", {"chat_id": uid, "text": "❌ Ошибка"})
                    waiting[uid] = None
                    continue
                
                # Команда /start
                if text == "/start":
                    # Проверка бана
                    user = conn.execute("SELECT banned FROM users WHERE user_id = ?", (uid,)).fetchone()
                    if user and user['banned']:
                        api("sendMessage", {"chat_id": uid, "text": "⛔ **Вы забанены!**\nОбратитесь к администратору.", "parse_mode": "HTML"})
                        continue
                    
                    # Проверка ОП
                    op = conn.execute("SELECT * FROM op_settings WHERE active = 1").fetchone()
                    if op:
                        cap = ("<tg-emoji emoji-id=\"6037249452824072506\">🔒</tg-emoji> **Привет!**\n"
                               "<tg-emoji emoji-id=\"6039630677182254664\">🔓</tg-emoji> **Подпишись для доступа!**")
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": cap, "parse_mode": "HTML", 
                                          "reply_markup": {"inline_keyboard": [[{"text": "✅ ПОДПИСАТЬСЯ", "url": op['link']}]]}})
                    else:
                        cap = ("<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет!**\n"
                               "<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала @OfficialPlutonium**\n"
                               "👇 **Используй кнопки ниже для навигации**")
                        api("sendPhoto", {"chat_id": uid, "photo": PHOTO_URL, "caption": cap, "parse_mode": "HTML", "reply_markup": main_kb(uid)})
                
                # Обработка ссылок на файлы
                elif text.startswith("/start "):
                    f_hash = text.split(" ")[1]
                    f = conn.execute("SELECT * FROM files WHERE hash = ?", (f_hash,)).fetchone()
                    if f:
                        cap = (f"<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> **Ваш Файл: {f['name']}**\n"
                               f"<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> **Buy plutonium - @PlutoniumllcBot**")
                        api("sendDocument", {"chat_id": uid, "document": f['file_id'], "caption": cap, "parse_mode": "HTML"})
                        conn.execute("UPDATE users SET downloads = downloads + 1 WHERE user_id = ?", (uid,))
                        conn.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (f_hash,))
                        conn.commit()
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
                 
