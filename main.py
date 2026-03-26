import os
import sqlite3
import secrets
import json
import logging
import urllib.request
import time
import re

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
OWNER_ID = int(os.environ.get("OWNER_ID", 1471307057))
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/OfficialPlutonium")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "OfficialPlutonium")
STORAGE_CHANNEL = os.environ.get("STORAGE_CHANNEL", "IllyaTelegram")
DB_PATH = "files.db"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
conn.row_factory = sqlite3.Row

conn.execute("""
    CREATE TABLE IF NOT EXISTS files (
        hash TEXT PRIMARY KEY,
        file_id TEXT,
        type TEXT,
        name TEXT,
        game TEXT,
        created_by INTEGER,
        downloads INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        is_premium INTEGER DEFAULT 0,
        invited_by INTEGER DEFAULT 0,
        total_invites INTEGER DEFAULT 0,
        total_downloads INTEGER DEFAULT 0,
        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        added_by INTEGER,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (OWNER_ID, OWNER_ID))
conn.commit()

# --- ФУНКЦИИ BOT API ---
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


def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return api("sendMessage", data)
# --- СБРОС ВЕБХУКА (ВАЖНО!) ---
try:
    api("deleteWebhook", {"drop_pending_updates": True})
    logger.info("✅ Webhook удалён")
except:
    pass

def send_document(chat_id, file_id, caption=None):
    data = {"chat_id": chat_id, "document": file_id, "parse_mode": "HTML"}
    if caption:
        data["caption"] = caption
    return api("sendDocument", data)

def get_chat_member(chat_id, user_id):
    return api("getChatMember", {"chat_id": chat_id, "user_id": user_id})

def answer_callback(callback_id, text=None, show_alert=False):
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text
    if show_alert:
        data["show_alert"] = True
    return api("answerCallbackQuery", data)

def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return api("editMessageText", data)

def get_updates(offset=None, timeout=30):
    data = {"timeout": timeout}
    if offset is not None:
        data["offset"] = offset
    return api("getUpdates", data)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    admin = conn.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    return admin is not None

def check_subscription(user_id):
    if not CHANNEL_ID:
        return True
    try:
        result = get_chat_member(CHANNEL_ID, user_id)
        if result.get('ok'):
            status = result['result']['status']
            return status in ('member', 'administrator', 'creator')
        return False
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return True

def save_user(user_id, username, first_name, last_name, is_premium, inviter_id=None):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, is_premium, invited_by) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, first_name, last_name, 1 if is_premium else 0, inviter_id or 0)
    )
    if inviter_id and inviter_id != user_id:
        conn.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter_id,))
    conn.commit()

def get_user(user_id):
    return conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

def get_all_games():
    return conn.execute("SELECT DISTINCT game FROM files WHERE game IS NOT NULL AND game != ''").fetchall()

def get_files_by_game(game):
    return conn.execute("SELECT hash, file_id, name FROM files WHERE game = ?", (game,)).fetchall()

def add_file(file_hash, file_id, file_type, name, game, created_by):
    conn.execute(
        "INSERT INTO files (hash, file_id, type, name, game, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        (file_hash, file_id, file_type, name, game, created_by)
    )
    conn.commit()

def increment_downloads(file_hash, user_id):
    conn.execute("UPDATE files SET downloads = downloads + 1 WHERE hash = ?", (file_hash,))
    conn.execute("UPDATE users SET total_downloads = total_downloads + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def get_stats():
    files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    invites = conn.execute("SELECT SUM(total_invites) FROM users").fetchone()[0] or 0
    downloads = conn.execute("SELECT SUM(downloads) FROM files").fetchone()[0] or 0
    premium = conn.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1").fetchone()[0]
    return {'files': files, 'users': users, 'invites': invites, 'downloads': downloads, 'premium': premium}

def cleanup_inactive():
    cursor = conn.execute("""
        DELETE FROM users 
        WHERE julianday('now') - julianday(last_active) > 30 
        AND user_id NOT IN (SELECT user_id FROM admins)
        AND user_id != ?
    """, (OWNER_ID,))
    conn.commit()
    return cursor.rowcount

def get_all_files():
    return conn.execute("SELECT name, game, downloads FROM files ORDER BY game, name").fetchall()

# --- ХРАНИЛИЩА ---
waiting_for_file = {}
waiting_for_broadcast = {}

# --- КЛАВИАТУРЫ ---
def main_keyboard(is_premium=False):
    if is_premium:
        return {
            "keyboard": [
                [{"text": "<tg-emoji emoji-id=\"5875008416132370818\">📁</tg-emoji> Игры", "parse_mode": "HTML"}],
                [{"text": "<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> Профиль", "parse_mode": "HTML"}, {"text": "🔗 Рефералка"}],
                [{"text": "❓ Помощь"}]
            ],
            "resize_keyboard": True
        }
    else:
        return {
            "keyboard": [
                [{"text": "📁 Игры"}],
                [{"text": "👋 Профиль"}, {"text": "🔗 Рефералка"}],
                [{"text": "❓ Помощь"}]
            ],
            "resize_keyboard": True
        }

def admin_keyboard(is_premium=False):
    return {
        "keyboard": [
            [{"text": "📁 Добавить чит"}, {"text": "📋 Список читов"}],
            [{"text": "👥 Пользователи"}, {"text": "📢 Рассылка"}],
            [{"text": "📊 Статистика"}, {"text": "🧹 Очистка"}],
            [{"text": "💾 Бэкап"}, {"text": "🔙 Главное меню"}]
        ],
        "resize_keyboard": True
    }

def subscribe_keyboard(is_premium=False):
    if is_premium:
        return {
            "inline_keyboard": [
                [{"text": "ПОДПИСАТЬСЯ", "url": CHANNEL_URL, "icon_custom_emoji_id": "5927118708873892465"}],
                [{"text": "ПРОВЕРИТЬ", "callback_data": "check_sub", "icon_custom_emoji_id": "5774022692642492953"}]
            ]
        }
    else:
        return {
            "inline_keyboard": [
                [{"text": "📢 ПОДПИСАТЬСЯ", "url": CHANNEL_URL}],
                [{"text": "🔄 ПРОВЕРИТЬ", "callback_data": "check_sub"}]
            ]
        }

def games_keyboard(games, is_premium=False):
    if not games:
        return None
    buttons = []
    for game in games:
        if is_premium:
            buttons.append([{"text": f"<tg-emoji emoji-id=\"5875008416132370818\">🎮</tg-emoji> {game['game']}", "parse_mode": "HTML"}])
        else:
            buttons.append([{"text": f"🎮 {game['game']}"}])
    buttons.append([{"text": "🔙 Главное меню"}])
    return {"keyboard": buttons, "resize_keyboard": True}

def cheats_keyboard(cheats):
    if not cheats:
        return None
    buttons = []
    for cheat in cheats:
        buttons.append([{"text": f"📄 {cheat['name'][:30]}", "callback_data": f"file_{cheat['hash']}"}])
    buttons.append([{"text": "🔙 Назад к играм"}])
    return {"keyboard": buttons, "resize_keyboard": True}

def file_footer(is_premium=False):
    if is_premium:
        return f"\n\n<tg-emoji emoji-id=\"6039573425268201570\">📤</tg-emoji> **Ваш Файл**\n<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji> **Buy plutonium** - @PlutoniumllcBot"
    else:
        return "\n\n📤 **Ваш Файл**\n🏪 **Buy plutonium** - @PlutoniumllcBot"

# --- ОБРАБОТЧИКИ ---
def process_message(chat_id, user_id, text, username, first_name, last_name, is_premium, message_id):
    try:
        # Рассылка
        if waiting_for_broadcast.get(user_id):
            if not is_admin(user_id):
                waiting_for_broadcast[user_id] = False
                return
            waiting_for_broadcast[user_id] = False
            users = conn.execute("SELECT user_id FROM users").fetchall()
            send_message(chat_id, f"🚀 Рассылка на {len(users)}...")
            sent = 0
            for user in users:
                try:
                    send_message(user['user_id'], text)
                    sent += 1
                except:
                    pass
            send_message(chat_id, f"✅ Готово! Отправлено: {sent}")
            return

        # Проверка подписки
        if not check_subscription(user_id):
            if is_premium:
                lock = '<tg-emoji emoji-id="6037249452824072506">🔒</tg-emoji>'
                unlock = '<tg-emoji emoji-id="6039630677182254664">🔓</tg-emoji>'
                msg_text = f"{lock} **Привет, {first_name}!**\n\n{unlock} **Подпишись на канал для доступа к читам.**"
            else:
                msg_text = f"🔒 **Привет, {first_name}!**\n\n🔓 **Подпишись на канал для доступа к читам.**"
            send_message(chat_id, msg_text, subscribe_keyboard(is_premium))
            return

        conn.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
        conn.commit()

        # --- КНОПКИ ---
        if text == "🔙 Главное меню":
            keyboard = admin_keyboard(is_premium) if is_admin(user_id) else main_keyboard(is_premium)
            send_message(chat_id, "Главное меню:", keyboard)

        elif text == "🔙 Назад к играм":
            games = get_all_games()
            keyboard = games_keyboard(games, is_premium)
            if keyboard:
                send_message(chat_id, "🎮 Выбери игру:", keyboard)
            else:
                send_message(chat_id, "📭 Нет игр", main_keyboard(is_premium))

        elif text == "👋 Профиль" or (text.startswith("<tg-emoji") and "Профиль" in text) or text == "👤 Профиль":
            user_data = get_user(user_id)
            if is_premium:
                profile_text = (
                    f"<tg-emoji emoji-id=\"6032693626394382504\">👤</tg-emoji> **Профиль**\n\n"
                    f"<tg-emoji emoji-id=\"5886505193180239900\">🆔</tg-emoji> ID: `{user_id}`\n"
                    f"<tg-emoji emoji-id=\"5879770735999717115\">📛</tg-emoji> Имя: {first_name or '?'}\n"
                    f"<tg-emoji emoji-id=\"5814247475141153332\">🔖</tg-emoji> Username: @{username or 'нет'}\n"
                    f"<tg-emoji emoji-id=\"6039802767931871481\">📥</tg-emoji> Файлов получено: {user_data.get('total_downloads', 0) if user_data else 0}"
                )
            else:
                profile_text = (
                    f"👤 **Профиль**\n\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"📛 Имя: {first_name or '?'}\n"
                    f"🔖 Username: @{username or 'нет'}\n"
                    f"📥 Файлов получено: {user_data.get('total_downloads', 0) if user_data else 0}"
                )
            send_message(chat_id, profile_text, main_keyboard(is_premium))

        elif text == "🔗 Рефералка":
            ref_link = f"https://t.me/PlutoniumCheatsBot?start=ref_{user_id}"
            send_message(chat_id, f"🔗 **Рефералка**\n\n`{ref_link}`", main_keyboard(is_premium))

        elif text == "❓ Помощь":
            send_message(chat_id, "📋 **Помощь**\n\n1. Игры\n2. Выбери игру\n3. Нажми на чит", main_keyboard(is_premium))

        elif text == "📁 Игры" or text == "🎮 Игры":
            games = get_all_games()
            keyboard = games_keyboard(games, is_premium)
            if keyboard:
                send_message(chat_id, "🎮 **Доступные игры:**", keyboard)
            else:
                send_message(chat_id, "📭 Пока нет читов.", main_keyboard(is_premium))

        elif text.startswith("🎮") or (text.startswith("<tg-emoji") and "Игры" not in text):
            game = text.split(" ", 1)[-1] if " " in text else text
            if game.startswith("<tg-emoji"):
                game = re.sub(r'<[^>]+>', '', game).strip()
            files = get_files_by_game(game)
            if files:
                keyboard = cheats_keyboard(files)
                send_message(chat_id, f"🎮 **{game}**\n\nВыбери чит:", keyboard)
            else:
                send_message(chat_id, f"❌ Для игры {game} пока нет читов.", games_keyboard(get_all_games(), is_premium))

        # --- АДМИН ---
        elif is_admin(user_id):
            if text == "📁 Добавить чит":
                waiting_for_file[user_id] = True
                send_message(chat_id, "📤 Отправь файл\nВ подписи: `Название | Игра`\nПример: `Aimbot | CS2`\n/cancel - отмена", admin_keyboard(is_premium))

            elif text == "📋 Список читов":
                files = get_all_files()
                if not files:
                    send_message(chat_id, "Пусто", admin_keyboard(is_premium))
                    return
                result = "📋 **Читы:**\n"
                for f in files:
                    result += f"\n🎮 {f['game']}\n  • {f['name']} (⬇️ {f['downloads']})"
                send_message(chat_id, result[:4000], admin_keyboard(is_premium))

            elif text == "👥 Пользователи":
                users = conn.execute("SELECT user_id, first_name, total_invites, total_downloads, is_premium FROM users ORDER BY total_downloads DESC").fetchall()
                result = "👥 **Пользователи:**\n\n"
                for i, u in enumerate(users[:30], 1):
                    name = u['first_name'] or str(u['user_id'])
                    premium = "👑" if u['is_premium'] else ""
                    result += f"{i}. {name} {premium} — пригл: {u['total_invites']} | ⬇️ {u['total_downloads']}\n"
                result += f"\n📊 Всего: {len(users)}"
                send_message(chat_id, result, admin_keyboard(is_premium))

            elif text == "📢 Рассылка":
                waiting_for_broadcast[user_id] = True
                send_message(chat_id, "📢 Отправь сообщение для рассылки", admin_keyboard(is_premium))

            elif text == "📊 Статистика":
                stats = get_stats()
                send_message(chat_id, f"📊 **Статистика**\n\n📁 Читов: {stats['files']}\n👥 Пользователей: {stats['users']}\n👑 Премиум: {stats['premium']}\n⬇️ Скачиваний: {stats['downloads']}\n🔗 Приглашений: {stats['invites']}", admin_keyboard(is_premium))

            elif text == "🧹 Очистка":
                deleted = cleanup_inactive()
                send_message(chat_id, f"✅ Удалено неактивных: {deleted}", admin_keyboard(is_premium))

            elif text == "💾 Бэкап":
                if os.path.exists(DB_PATH):
                    with open(DB_PATH, 'rb') as f:
                        url = f"{API_URL}/sendDocument"
                        boundary = '--' + secrets.token_hex(16)
                        body_parts = []
                        body_parts.append(f'--{boundary}')
                        body_parts.append('Content-Disposition: form-data; name="chat_id"')
                        body_parts.append('')
                        body_parts.append(str(chat_id))
                        body_parts.append(f'--{boundary}')
                        body_parts.append('Content-Disposition: form-data; name="document"; filename="files.db"')
                        body_parts.append('Content-Type: application/octet-stream')
                        body_parts.append('')
                        body_parts.append(f.read())
                        body_parts.append(f'--{boundary}--')
                        body = b'\r\n'.join([p.encode() if isinstance(p, str) else p for p in body_parts])
                        req = urllib.request.Request(url, data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}, method='POST')
                        urllib.request.urlopen(req, timeout=30)
                else:
                    send_message(chat_id, "Нет файла")

    except Exception as e:
        logger.error(f"Process error: {e}")

def process_callback(callback_id, chat_id, message_id, data, user_id, is_premium):
    try:
        if data == "check_sub":
            subscribed = check_subscription(user_id)
            if subscribed:
                user_data = get_user(user_id)
                first_name = user_data.get('first_name', 'Пользователь') if user_data else 'Пользователь'
                if is_premium:
                    text = (
                        f"<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет, {first_name}!**\n\n"
                        f"<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала** @OfficialPlutonium\n"
                        f"<tg-emoji emoji-id=\"5875008416132370818\">📁</tg-emoji> **Используй кнопки ниже**"
                    )
                else:
                    text = f"👋 **Привет, {first_name}!**\n\n🙂 **Я храню файлы с канала** @OfficialPlutonium\n📁 **Используй кнопки ниже**"
                keyboard = admin_keyboard(is_premium) if is_admin(user_id) else main_keyboard(is_premium)
                edit_message(chat_id, message_id, text, keyboard)
                answer_callback(callback_id, "✅ Подписка подтверждена!")
            else:
                answer_callback(callback_id, "❌ Вы еще не подписались!", True)
        elif data.startswith("file_"):
            file_hash = data.split("_")[1]
            file_data = conn.execute("SELECT file_id, name FROM files WHERE hash = ?", (file_hash,)).fetchone()
            if file_data:
                increment_downloads(file_hash, user_id)
                footer = file_footer(is_premium)
                send_document(chat_id, file_data['file_id'], f"✅ {file_data['name']} отправлен!{footer}")
                answer_callback(callback_id, f"✅ {file_data['name']} отправлен!")
            else:
                answer_callback(callback_id, "❌ Файл не найден", True)
    except Exception as e:
        logger.error(f"Callback error: {e}")

def process_document(chat_id, user_id, file_id, file_name, caption):
    try:
        if not waiting_for_file.get(user_id):
            return
        if not is_admin(user_id):
            waiting_for_file[user_id] = False
            return

        waiting_for_file[user_id] = False

        name = file_name
        game = "Без игры"
        if caption and "|" in caption:
            parts = caption.split("|")
            name = parts[0].strip()
            game = parts[1].strip()
        elif caption:
            name = caption.strip()

        file_hash = secrets.token_urlsafe(8)
        add_file(file_hash, file_id, "doc", name, game, user_id)

        user = conn.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,)).fetchone()
        is_premium = user['is_premium'] if user else False

        if is_premium:
            text = (
                f"<tg-emoji emoji-id=\"6039573425268201570\">✅</tg-emoji> **Чит добавлен!**\n\n"
                f"<tg-emoji emoji-id=\"5879770735999717115\">📄</tg-emoji> {name}\n"
                f"<tg-emoji emoji-id=\"5875008416132370818\">🎮</tg-emoji> {game}\n\n"
                f"<tg-emoji emoji-id=\"6032693626394382504\">🔗</tg-emoji> `https://t.me/PlutoniumCheatsBot?start={file_hash}`"
            )
        else:
            text = f"✅ **Чит добавлен!**\n\n📄 {name}\n🎮 {game}\n\n🔗 `https://t.me/PlutoniumCheatsBot?start={file_hash}`"

        send_message(chat_id, text, admin_keyboard(is_premium))

    except Exception as e:
        logger.error(f"Document error: {e}")
        send_message(chat_id, f"❌ Ошибка: {e}")

# --- ГЛАВНЫЙ ЦИКЛ ---
def main():
    logger.info("🚀 Запуск Plutonium Bot")
    logger.info(f"👑 Владелец: {OWNER_ID}")
    logger.info(f"📢 Канал: {CHANNEL_ID}")

    offset = 0
    while True:
        try:
            updates = get_updates(offset, timeout=30)
            if updates.get('ok') and updates.get('result'):
                for update in updates['result']:
                    offset = update['update_id'] + 1

                    # Callback
                    if 'callback_query' in update:
                        cb = update['callback_query']
                        user = cb['from']
                        process_callback(
                            cb['id'],
                            cb['message']['chat']['id'],
                            cb['message']['message_id'],
                            cb['data'],
                            user['id'],
                            user.get('is_premium', False)
                        )

                    # Сообщение
                    elif 'message' in update:
                        msg = update['message']
                        chat_id = msg['chat']['id']
                        user = msg['from']
                        user_id = user['id']
                        username = user.get('username', '')
                        first_name = user.get('first_name', '')
                        last_name = user.get('last_name', '')
                        is_premium = user.get('is_premium', False)

                        if not get_user(user_id):
                            save_user(user_id, username, first_name, last_name, is_premium)

                        if 'text' in msg and msg['text'].startswith('/start'):
                            args = msg['text'].replace('/start', '').strip()
                            inviter_id = None
                            if args.startswith('ref_'):
                                try:
                                    inviter_id = int(args.split('_')[1])
                                    if inviter_id != user_id:
                                        save_user(user_id, username, first_name, last_name, is_premium, inviter_id)
                                except:
                                    pass

                            subscribed = check_subscription(user_id)
                            if not subscribed:
                                if is_premium:
                                    lock = '<tg-emoji emoji-id="6037249452824072506">🔒</tg-emoji>'
                                    unlock = '<tg-emoji emoji-id="6039630677182254664">🔓</tg-emoji>'
                                    text = f"{lock} **Привет, {first_name}!**\n\n{unlock} **Подпишись на канал для доступа к читам.**"
                                else:
                                    text = f"🔒 **Привет, {first_name}!**\n\n🔓 **Подпишись на канал для доступа к читам.**"
                                send_message(chat_id, text, subscribe_keyboard(is_premium))
                            else:
                                if is_premium:
                                    text = (
                                        f"<tg-emoji emoji-id=\"6041921818896372382\">👋</tg-emoji> **Привет, {first_name}!**\n\n"
                                        f"<tg-emoji emoji-id=\"5289930378885214069\">🙂</tg-emoji> **Я храню файлы с канала** @OfficialPlutonium\n"
                                        f"<tg-emoji emoji-id=\"5875008416132370818\">📁</tg-emoji> **Используй кнопки ниже**"
                                    )
                                else:
                                    text = f"👋 **Привет, {first_name}!**\n\n🙂 **Я храню файлы с канала** @OfficialPlutonium\n📁 **Используй кнопки ниже**"

                                user_data = get_user(user_id)
                                invites = user_data['total_invites'] if user_data else 0
                                text += f"\n\n👥 Приглашений: {invites}"
                                keyboard = admin_keyboard(is_premium) if is_admin(user_id) else main_keyboard(is_premium)
                                send_message(chat_id, text, keyboard)

                        elif 'text' in msg:
                            process_message(
                                chat_id, user_id, msg['text'],
                                username, first_name, last_name,
                                is_premium, msg['message_id']
                            )

                        elif 'document' in msg:
                            file_id = msg['document']['file_id']
                            file_name = msg['document'].get('file_name', 'file')
                            caption = msg.get('caption')
                            process_document(chat_id, user_id, file_id, file_name, caption)

            time.sleep(1)

        except Exception as e:
            logger.error(f"Main loop error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
