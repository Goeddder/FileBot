import os
import sqlite3
import secrets
import asyncio
import shutil
import logging
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Tuple

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from pyrogram.errors import UserNotParticipant, FloodWait

# --- НАСТРОЙКИ ---
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
ADMIN_ID = int(os.environ.get("OWNER_ID", 1471307057))
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/OfficialPlutonium")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@OfficialPlutonium")
STORAGE_CHANNEL = os.environ.get("STORAGE_CHANNEL", "@IllyaTelegram")

DB_PATH = "files.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- БД С ПУЛОМ СОЕДИНЕНИЙ ---
class Database:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_db()
        return cls._instance
    
    def _init_db(self):
        self.conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                hash TEXT PRIMARY KEY,
                remote_msg_id INTEGER,
                type TEXT,
                name TEXT,
                game TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                invited_by INTEGER DEFAULT 0,
                total_invites INTEGER DEFAULT 0,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()
        cursor.close()
        logger.info("✅ База данных готова")
    
    def execute(self, query, params=()):
        cursor = self.conn.cursor()
        try:
            cursor.execute(query, params)
            self.conn.commit()
            return cursor
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def fetch_one(self, query, params=()):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()
        cursor.close()
        return result
    
    def fetch_all(self, query, params=()):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchall()
        cursor.close()
        return result

db = Database()
app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

waiting_for_backup = {}
waiting_for_file = {}


# --- КЛАВИАТУРЫ (ОБЫЧНЫЕ КНОПКИ) ---
def get_main_keyboard():
    """Главная клавиатура с кнопками"""
    buttons = [
        [KeyboardButton("🎮 Игры"), KeyboardButton("📁 Мои читы")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("🔗 Рефералка")],
        [KeyboardButton("❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_admin_keyboard():
    """Админ-панель с кнопками"""
    buttons = [
        [KeyboardButton("📁 Добавить чит"), KeyboardButton("📋 Список читов")],
        [KeyboardButton("👥 Пользователи"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("👑 Админы"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("🧹 Очистка"), KeyboardButton("💾 Бэкап БД")],
        [KeyboardButton("🔙 Главное меню")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_games_keyboard():
    """Клавиатура с играми"""
    files = db.fetch_all("SELECT DISTINCT game FROM files WHERE game IS NOT NULL AND game != ''")
    buttons = []
    for file in files:
        game = file[0]
        buttons.append([KeyboardButton(f"🎮 {game}")])
    buttons.append([KeyboardButton("🔙 Назад")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True) if buttons else None


def get_cheats_keyboard(game: str):
    """Клавиатура с читами для конкретной игры"""
    files = db.fetch_all("SELECT hash, name FROM files WHERE game = ?", (game,))
    buttons = []
    for file in files:
        name = file[1][:30]
        buttons.append([KeyboardButton(f"📄 {name}")])
    buttons.append([KeyboardButton("🔙 Назад")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


# --- ФУНКЦИИ ---
async def check_sub(client, user_id):
    try:
        await client.get_chat_member(CHANNEL_ID, user_id)
        return True
    except UserNotParticipant:
        return False
    except:
        return True


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом"""
    if user_id == ADMIN_ID:
        return True
    admin = db.fetch_one("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return admin is not None


# --- КОМАНДЫ И КНОПКИ ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user = message.from_user
    inviter_id = None
    
    # Рефералка
    if len(message.command) > 1:
        ref = message.command[1]
        if ref.startswith("ref_"):
            try:
                inviter_id = int(ref.split("_")[1])
                if inviter_id == user.id:
                    inviter_id = None
            except:
                pass
    
    # Сохраняем юзера
    db.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, invited_by) VALUES (?, ?, ?, ?)",
        (user.id, user.username, user.first_name, inviter_id or 0)
    )
    
    # Обновляем счетчик приглашений
    if inviter_id and inviter_id != user.id:
        db.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter_id,))
        db.execute("INSERT INTO invites (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user.id))
    
    # Проверка подписки
    if not await check_sub(client, user.id):
        sub_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL)]])
        return await message.reply(
            f"👋 Привет, {user.first_name}!\nПодпишись на канал для доступа к читам.",
            reply_markup=sub_kb
        )
    
    # Отправляем приветствие с кнопками
    keyboard = get_admin_keyboard() if is_admin(user.id) else get_main_keyboard()
    
    await message.reply(
        f"🎮 **Plutonium Cheats**\n\n"
        f"👋 Привет, {user.first_name}!\n\n"
        f"📁 Здесь ты можешь скачать читы для игр.\n\n"
        f"Используй кнопки ниже:",
        reply_markup=keyboard
    )


@app.on_message(filters.text & filters.private)
async def handle_buttons(client, message):
    user_id = message.from_user.id
    text = message.text
    
    # Проверка подписки
    if not await check_sub(client, user_id):
        sub_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL)]])
        return await message.reply("⚠️ Подпишись на канал!", reply_markup=sub_kb)
    
    # --- ГЛАВНОЕ МЕНЮ ---
    if text == "🔙 Назад" or text == "🔙 Главное меню":
        keyboard = get_admin_keyboard() if is_admin(user_id) else get_main_keyboard()
        return await message.reply("🔙 Главное меню:", reply_markup=keyboard)
    
    # --- ПОЛЬЗОВАТЕЛЬСКИЕ КНОПКИ ---
    if text == "🎮 Игры":
        keyboard = get_games_keyboard()
        if keyboard:
            await message.reply("🎮 **Выбери игру:**", reply_markup=keyboard)
        else:
            await message.reply("📭 Пока нет доступных читов.", reply_markup=get_main_keyboard())
    
    elif text == "👤 Профиль":
        user_data = db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        invites = user_data['total_invites'] if user_data else 0
        created = user_data['created_at'] if user_data else "?"
        
        await message.reply(
            f"👤 **Твой профиль**\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"👥 Приглашений: {invites}\n"
            f"📅 Дата регистрации: {created}",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "🔗 Рефералка":
        ref_link = f"https://t.me/{app.me().username}?start=ref_{user_id}"
        await message.reply(
            f"🔗 **Твоя реферальная ссылка:**\n\n"
            f"`{ref_link}`\n\n"
            f"Приглашай друзей и получай доступ к эксклюзивным читам!",
            reply_markup=get_main_keyboard()
        )
    
    elif text == "📁 Мои читы":
        files = db.fetch_all("SELECT name, game FROM files WHERE created_by = ?", (user_id,))
        if not files:
            await message.reply("📭 Ты еще не добавил ни одного чита.", reply_markup=get_main_keyboard())
        else:
            text = "📁 **Твои читы:**\n\n"
            for file in files:
                text += f"• {file['name']} ({file['game']})\n"
            await message.reply(text, reply_markup=get_main_keyboard())
    
    elif text == "❓ Помощь":
        await message.reply(
            "📋 **Как пользоваться ботом:**\n\n"
            "1️⃣ Нажми «🎮 Игры» — выбери игру\n"
            "2️⃣ Нажми на название чита — получишь файл\n"
            "3️⃣ Используй рефералку, чтобы приглашать друзей\n\n"
            "🔗 **Для админов:**\n"
            "• Отправь файл с названием игры в подписи\n"
            "• Формат: `Название чита | Название игры`\n"
            "• Пример: `Aimbot | CS2`",
            reply_markup=get_main_keyboard()
        )
    
    # --- ВЫБОР ИГРЫ ---
    elif text.startswith("🎮 "):
        game = text[2:]
        files = db.fetch_all("SELECT hash, name FROM files WHERE game = ?", (game,))
        if files:
            keyboard = get_cheats_keyboard(game)
            await message.reply(f"🎮 **{game}**\nВыбери чит:", reply_markup=keyboard)
        else:
            await message.reply(f"❌ Для игры {game} пока нет читов.", reply_markup=get_games_keyboard())
    
    # --- ВЫБОР ЧИТА ---
    elif text.startswith("📄 "):
        cheat_name = text[2:]
        files = db.fetch_all("SELECT hash, name FROM files WHERE name = ?", (cheat_name,))
        
        if files:
            file_hash = files[0]['hash']
            file_data = db.fetch_one("SELECT remote_msg_id FROM files WHERE hash = ?", (file_hash,))
            
            if file_data:
                try:
                    await client.copy_message(user_id, STORAGE_CHANNEL, file_data[0])
                except Exception as e:
                    await message.reply(f"❌ Ошибка загрузки: {e}")
            else:
                await message.reply("❌ Файл не найден")
        else:
            await message.reply("❌ Чит не найден")
    
    # --- АДМИН КНОПКИ ---
    elif is_admin(user_id):
        if text == "📁 Добавить чит":
            waiting_for_file[user_id] = True
            await message.reply(
                "📤 **Отправь файл с читом**\n\n"
                "В подписи укажи:\n"
                "`Название чита | Название игры`\n\n"
                "Пример: `Aimbot | CS2`\n\n"
                "Для отмены нажми /cancel",
                reply_markup=get_admin_keyboard()
            )
        
        elif text == "📋 Список читов":
            files = db.fetch_all("SELECT name, game FROM files ORDER BY game, name")
            if not files:
                await message.reply("📭 База читов пуста.", reply_markup=get_admin_keyboard())
            else:
                text = "📋 **Все читы:**\n\n"
                current_game = ""
                for file in files:
                    if file['game'] != current_game:
                        current_game = file['game']
                        text += f"\n🎮 **{current_game}**\n"
                    text += f"  • {file['name']}\n"
                await message.reply(text, reply_markup=get_admin_keyboard())
        
        elif text == "👥 Пользователи":
            users = db.fetch_all("SELECT user_id, first_name, total_invites FROM users ORDER BY total_invites DESC")
            text = "👥 **Пользователи:**\n\n"
            for i, user in enumerate(users[:20], 1):
                name = user['first_name'] or str(user['user_id'])
                text += f"{i}. {name} — пригл: {user['total_invites']}\n"
            text += f"\nВсего: {len(users)}"
            await message.reply(text, reply_markup=get_admin_keyboard())
        
        elif text == "📢 Рассылка":
            waiting_for_broadcast = True
            await message.reply(
                "📢 **Рассылка**\n\n"
                "Отправь сообщение для рассылки.\n"
                "Для отмены нажми /cancel",
                reply_markup=get_admin_keyboard()
            )
        
        elif text == "👑 Админы":
            admins = db.fetch_all("SELECT user_id FROM admins")
            admin_list = [ADMIN_ID] + [a[0] for a in admins]
            text = "👑 **Администраторы:**\n\n"
            for aid in admin_list:
                user = db.fetch_one("SELECT first_name, username FROM users WHERE user_id = ?", (aid,))
                name = user['first_name'] if user else str(aid)
                text += f"• {name} (`{aid}`)\n"
            await message.reply(text, reply_markup=get_admin_keyboard())
        
        elif text == "📊 Статистика":
            files_count = db.fetch_one("SELECT COUNT(*) FROM files")[0]
            users_count = db.fetch_one("SELECT COUNT(*) FROM users")[0]
            invites_total = db.fetch_one("SELECT SUM(total_invites) FROM users")[0] or 0
            
            await message.reply(
                f"📊 **Статистика бота**\n\n"
                f"📁 Читов: {files_count}\n"
                f"👥 Пользователей: {users_count}\n"
                f"🔗 Всего приглашений: {invites_total}\n"
                f"💾 База: SQLite",
                reply_markup=get_admin_keyboard()
            )
        
        elif text == "🧹 Очистка":
            # Очистка неактивных (30 дней)
            db.execute("""
                DELETE FROM users 
                WHERE julianday('now') - julianday(last_active) > 30 
                AND user_id NOT IN (SELECT user_id FROM admins)
                AND user_id != ?
            """, (ADMIN_ID,))
            deleted = db.conn.total_changes
            await message.reply(f"🧹 Удалено неактивных пользователей: {deleted}", reply_markup=get_admin_keyboard())
        
        elif text == "💾 Бэкап БД":
            if os.path.exists(DB_PATH):
                await message.reply_document(DB_PATH, caption="📦 Бэкап базы данных")
            else:
                await message.reply("❌ Файл базы не найден")
    
    else:
        # Поиск чита по названию игры
        games = db.fetch_all("SELECT DISTINCT game FROM files WHERE LOWER(game) LIKE ?", (f"%{text.lower()}%",))
        if games:
            keyboard = ReplyKeyboardMarkup(
                [[KeyboardButton(f"🎮 {g[0]}")] for g in games[:10]] + [[KeyboardButton("🔙 Назад")]],
                resize_keyboard=True
            )
            await message.reply(f"🔍 Найдено игр: {len(games)}\nВыбери:", reply_markup=keyboard)
        else:
            await message.reply("❌ Не понял команду. Используй кнопки.", reply_markup=get_main_keyboard())


# --- ЗАГРУЗКА ФАЙЛОВ АДМИНАМИ ---
@app.on_message((filters.document | filters.video | filters.photo) & filters.private)
async def handle_upload(client, message):
    user_id = message.from_user.id
    
    if not waiting_for_file.get(user_id, False):
        return
    
    if not is_admin(user_id):
        waiting_for_file[user_id] = False
        return await message.reply("⛔ У вас нет прав на загрузку!")
    
    status = await message.reply("⏳ Сохраняю чит...")
    
    try:
        # Копируем в хранилище
        sent = await message.copy(STORAGE_CHANNEL)
        file_hash = secrets.token_urlsafe(8)
        
        # Определяем тип
        if message.document:
            file_type = "doc"
            name = message.document.file_name
        elif message.video:
            file_type = "video"
            name = message.video.file_name or "Video"
        else:
            file_type = "photo"
            name = "Photo"
        
        # Парсим название и игру из подписи
        game = "Без игры"
        if message.caption:
            if "|" in message.caption:
                parts = message.caption.split("|")
                name = parts[0].strip()
                game = parts[1].strip()
            else:
                name = message.caption.strip()
        
        # Сохраняем в БД
        db.execute(
            "INSERT INTO files (hash, remote_msg_id, type, name, game, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (file_hash, sent.id, file_type, name, game, user_id)
        )
        
        bot_username = (await app.me()).username
        
        await status.edit_text(
            f"✅ **Чит сохранен!**\n\n"
            f"📄 Название: {name}\n"
            f"🎮 Игра: {game}\n"
            f"🔗 Ссылка: `https://t.me/{bot_username}?start={file_hash}`"
        )
        
        waiting_for_file[user_id] = False
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await status.edit_text(f"❌ Ошибка: {e}")
        waiting_for_file[user_id] = False


# --- РАССЫЛКА ---
waiting_for_broadcast = False
broadcast_message = None

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client, message):
    global waiting_for_broadcast, waiting_for_file
    user_id = message.from_user.id
    
    if waiting_for_file.get(user_id):
        waiting_for_file[user_id] = False
        await message.reply("✅ Загрузка отменена")
    elif waiting_for_broadcast:
        waiting_for_broadcast = False
        await message.reply("✅ Рассылка отменена")
    else:
        await message.reply("Нет активных операций")


@app.on_message(filters.text & filters.private)
async def handle_broadcast(client, message):
    global waiting_for_broadcast
    
    if not waiting_for_broadcast:
        return
    
    if not is_admin(message.from_user.id):
        waiting_for_broadcast = False
        return
    
    waiting_for_broadcast = False
    
    users = db.fetch_all("SELECT user_id FROM users")
    if not users:
        return await message.reply("Нет пользователей для рассылки")
    
    status = await message.reply(f"🚀 Начинаю рассылку на {len(users)} пользователей...")
    
    sent = 0
    failed = 0
    
    for i, user in enumerate(users):
        try:
            await message.copy(user[0])
            sent += 1
        except Exception:
            failed += 1
        
        if (i + 1) % 10 == 0:
            await status.edit_text(f"Прогресс: {sent + failed}/{len(users)} (✅ {sent} | ❌ {failed})")
            await asyncio.sleep(0.5)
    
    await status.edit_text(f"✅ Рассылка завершена!\n✅ Успешно: {sent}\n❌ Ошибок: {failed}")


# --- ВОССТАНОВЛЕНИЕ БД ---
@app.on_message(filters.command("restore") & filters.user(ADMIN_ID))
async def restore_req(client, message):
    waiting_for_backup[message.from_user.id] = True
    await message.reply("📤 Пришли файл `files.db` для восстановления.")


@app.on_message(filters.document & filters.user(ADMIN_ID))
async def handle_restore(client, message):
    user_id = message.from_user.id
    
    if user_id in waiting_for_backup and "files.db" in message.document.file_name:
        status = await message.reply("⏳ Восстановление...")
        try:
            temp_path = "temp_restore.db"
            await message.download(file_name=temp_path)
            
            # Проверяем структуру
            check_conn = sqlite3.connect(temp_path)
            check_conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, remote_msg_id INTEGER, type TEXT, name TEXT, game TEXT)")
            check_conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
            f_count = check_conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            u_count = check_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            check_conn.close()
            
            # Заменяем
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            shutil.move(temp_path, DB_PATH)
            
            # Пересоздаем подключение
            db.conn.close()
            db._init_db()
            
            del waiting_for_backup[user_id]
            await status.edit_text(f"✅ Восстановлено!\nФайлов: {f_count}\nЮзеров: {u_count}")
            
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {e}")


# --- ЗАПУСК ---
if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    app.run()
