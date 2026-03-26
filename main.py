import os
import sqlite3
import secrets
import json
import logging
import urllib.request
import time

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw"  # ЗАМЕНИ НА НОВЫЙ ТОКЕН
OWNER_ID = 1471307057
CHANNEL_URL = "https://t.me/OfficialPlutonium"
CHANNEL_ID = "OfficialPlutonium"
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

# --- СБРОС ---
logger.info("🔄 Сброс...")
api("deleteWebhook", {"drop_pending_updates": True})
time.sleep(2)
api("getUpdates", {"offset": -1})
time.sleep(1)
logger.info("✅ Сброс завершен")

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
conn.row_factory = sqlite3.Row

conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, file_id TEXT, name TEXT, game TEXT)")
conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT)")
conn.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)", (OWNER_ID, "Admin"))
conn.commit()

# --- ФУНКЦИИ ---
def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    return api("sendMessage", data)

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
        data["reply_markup"] = json.dumps(reply_markup)
    return api("editMessageText", data)

def get_updates(offset=None):
    data = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
    if offset:
        data["offset"] = offset
    return api("getUpdates", data)

# --- КЛАВИАТУРЫ ---
main_kb = {
    "keyboard": [
        [{"text": "🎮 Игры"}],
        [{"text": "👤 Профиль"}, {"text": "🔗 Рефералка"}],
        [{"text": "❓ Помощь"}]
    ],
    "resize_keyboard": True
}

sub_kb = {
    "inline_keyboard": [
        [{"text": "📢 ПОДПИСАТЬСЯ", "url": CHANNEL_URL}],
        [{"text": "🔄 ПРОВЕРИТЬ", "callback_data": "check"}]
    ]
}

# --- ПРОВЕРКА ПОДПИСКИ ---
def check_sub(user_id):
    try:
        r = api("getChatMember", {"chat_id": CHANNEL_ID, "user_id": user_id})
        if r.get('ok'):
            status = r['result']['status']
            return status in ['member', 'administrator', 'creator']
    except:
        pass
    return True  # Если ошибка - пропускаем

# --- ГЛАВНЫЙ ЦИКЛ ---
def main():
    logger.info("🚀 Запуск...")
    offset = 0
    
    while True:
        try:
            updates = get_updates(offset)
            
            if updates.get('ok') and updates.get('result'):
                for update in updates['result']:
                    offset = update['update_id'] + 1
                    
                    # Callback
                    if 'callback_query' in update:
                        cb = update['callback_query']
                        user_id = cb['from']['id']
                        chat_id = cb['message']['chat']['id']
                        msg_id = cb['message']['message_id']
                        data = cb['data']
                        
                        if data == 'check':
                            if check_sub(user_id):
                                edit_message(chat_id, msg_id, "✅ Подписка подтверждена! Используй кнопки:", main_kb)
                                answer_callback(cb['id'], "✅ Подписка подтверждена!")
                            else:
                                answer_callback(cb['id'], "❌ Подпишись на канал!", True)
                    
                    # Сообщение
                    elif 'message' in update:
                        msg = update['message']
                        chat_id = msg['chat']['id']
                        user_id = msg['from']['id']
                        text = msg.get('text', '')
                        first_name = msg['from'].get('first_name', '')
                        
                        # Сохраняем пользователя
                        conn.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)", (user_id, first_name))
                        conn.commit()
                        
                        # Проверка подписки
                        if not check_sub(user_id):
                            send_message(chat_id, f"🔒 Привет, {first_name}!\n\n🔓 Подпишись на канал:", sub_kb)
                            continue
                        
                        # Команды
                        if text == '/start':
                            send_message(chat_id, f"👋 Привет, {first_name}!\n\n📁 Plutonium Cheats\nИспользуй кнопки:", main_kb)
                        
                        elif text == '🎮 Игры':
                            games = conn.execute("SELECT DISTINCT game FROM files").fetchall()
                            if games:
                                kb = {"keyboard": [[{"text": f"🎮 {g['game']}"}] for g in games] + [[{"text": "🔙 Главное меню"}]], "resize_keyboard": True}
                                send_message(chat_id, "🎮 Игры:", kb)
                            else:
                                send_message(chat_id, "📭 Нет игр", main_kb)
                        
                        elif text.startswith('🎮 '):
                            game = text[3:]
                            files = conn.execute("SELECT hash, name FROM files WHERE game = ?", (game,)).fetchall()
                            if files:
                                kb = {"keyboard": [[{"text": f"📄 {f['name'][:30]}", "callback_data": f"file_{f['hash']}"}] for f in files] + [[{"text": "🔙 Назад к играм"}]], "resize_keyboard": True}
                                send_message(chat_id, f"🎮 {game}\nВыбери чит:", kb)
                            else:
                                send_message(chat_id, f"❌ Нет читов для {game}", main_kb)
                        
                        elif text == '👤 Профиль':
                            user = conn.execute("SELECT total_invites FROM users WHERE user_id = ?", (user_id,)).fetchone()
                            invites = user['total_invites'] if user else 0
                            send_message(chat_id, f"👤 Профиль\n\n🆔 ID: {user_id}\n👥 Приглашений: {invites}", main_kb)
                        
                        elif text == '🔗 Рефералка':
                            send_message(chat_id, f"🔗 Рефералка\n\n`https://t.me/PlutoniumCheatsBot?start=ref_{user_id}`", main_kb)
                        
                        elif text == '❓ Помощь':
                            send_message(chat_id, "📋 Помощь\n\n1. Игры\n2. Выбери игру\n3. Нажми на чит", main_kb)
                        
                        elif text == '🔙 Главное меню':
                            send_message(chat_id, "Главное меню:", main_kb)
                        
                        elif text == '🔙 Назад к играм':
                            games = conn.execute("SELECT DISTINCT game FROM files").fetchall()
                            if games:
                                kb = {"keyboard": [[{"text": f"🎮 {g['game']}"}] for g in games] + [[{"text": "🔙 Главное меню"}]], "resize_keyboard": True}
                                send_message(chat_id, "🎮 Игры:", kb)
                            else:
                                send_message(chat_id, "📭 Нет игр", main_kb)
            
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
