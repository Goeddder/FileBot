import os
import sqlite3
import secrets
import asyncio
import shutil
import logging
from datetime import datetime

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
OWNER_ID = int(os.environ.get("OWNER_ID", 1471307057))
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/OfficialPlutonium")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@OfficialPlutonium")
STORAGE_CHANNEL = os.environ.get("STORAGE_CHANNEL", "@IllyaTelegram")

DB_PATH = "files.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- БАЗА ДАННЫХ ---
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
        
        # Таблица файлов
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
        
        # Таблица пользователей
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
        
        # Таблица приглашений
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER,
                invited_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица администраторов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
        cursor.close()
        
        # Добавляем владельца в админы
        self._add_owner()
        logger.info("✅ База данных готова")
    
    def _add_owner(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (OWNER_ID,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO admins (user_id, added_by) VALUES (?, ?)", (OWNER_ID, OWNER_ID))
            self.conn.commit()
        cursor.close()
    
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


# --- КЛАВИАТУРЫ ---
def get_main_keyboard():
    """Главная клавиатура для всех пользователей"""
    buttons = [
        [KeyboardButton("🎮 Игры")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("🔗 Рефералка")],
        [KeyboardButton("❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_admin_keyboard():
    """Админ-панель"""
    buttons = [
        [KeyboardButton("📁 Добавить чит"), KeyboardButton("📋 Список читов")],
        [KeyboardButton("👥 Пользователи"), KeyboardButton("📢 Рассылка")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("🧹 Очистка")],
        [KeyboardButton("💾 Бэкап"), KeyboardButton("🔙 Главное меню")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_games_keyboard():
    """Клавиатура с играми"""
    files = db.fetch_all("SELECT DISTINCT game FROM files WHERE game IS NOT NULL AND game != ''")
    if not files:
        return None
    
    buttons = []
    for file in files:
        game = file['game']
        buttons.append([KeyboardButton(f"🎮 {game}")])
    buttons.append([KeyboardButton("🔙 Главное меню")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def get_cheats_keyboard(game):
    """Клавиатура с читами для игры"""
    files = db.fetch_all("SELECT hash, name FROM files WHERE game = ?", (game,))
    if not files:
        return None
    
    buttons = []
    for file in files:
        name = file['name'][:30]
        buttons.append([KeyboardButton(f"📄 {name}")])
    buttons.append([KeyboardButton("🔙 Назад к играм")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


# --- ФУНКЦИИ ---
async def check_sub(client, user_id):
    """Проверка подписки на канал"""
    try:
        member = await client.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except UserNotParticipant:
        return False
    except Exception:
        return True


def is_admin(user_id):
    """Проверка, является ли пользователь админом"""
    if user_id == OWNER_ID:
        return True
    admin = db.fetch_one("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return admin is not None


# --- ОБРАБОТЧИКИ ---
app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user = message.from_user
    inviter_id = None
    
    # Обработка реферальной ссылки
    if len(message.command) > 1:
        ref = message.command[1]
        if ref.startswith("ref_"):
            try:
                inviter_id = int(ref.split("_")[1])
                if inviter_id == user.id:
                    inviter_id = None
            except:
                pass
    
    # Сохраняем пользователя
    db.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, invited_by) VALUES (?, ?, ?, ?)",
        (user.id, user.username, user.first_name, inviter_id or 0)
    )
    
    # Обновляем счетчик приглашений у пригласившего
    if inviter_id and inviter_id != user.id:
        db.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter_id,))
        db.execute("INSERT INTO invites (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user.id))
    
    # Проверка подписки
    if not await check_sub(client, user.id):
        sub_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_URL)]])
        await message.reply(
            f"👋 Привет, {user.first_name}!\n\n"
            f"🔒 Для доступа к читам нужно подписаться на наш канал.",
            reply_markup=sub_kb
        )
        return
    
    # Приветствие с кнопками
    keyboard = get_admin_keyboard() if is_admin(user.id) else get_main_keyboard()
    
    user_data = db.fetch_one("SELECT total_invites FROM users WHERE user_id = ?", (user.id,))
    invites = user_data['total_invites'] if user_data else 0
    
    await message.reply(
        f"🎮 **Plutonium Cheats**\n\n"
        f"👋 Добро пожаловать, {user.first_name}!\n\n"
        f"📁 Здесь ты можешь скачать читы для игр.\n"
        f"👥 Твоих приглашений: {invites}\n\n"
        f"📌 Используй кнопки ниже для навигации.",
        reply_markup=keyboard
    )


@app.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.from_user.id
    text = message.text
    
    # Проверка подписки
    if not await check_sub(client, user_id):
        sub_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_URL)]])
        await message.reply("⚠️ Подпишись на канал для доступа!", reply_markup=sub_kb)
        return
    
    # --- ОБРАБОТКА КНОПОК ---
    
    # Главное меню
    if text == "🔙 Главное меню":
        keyboard = get_admin_keyboard() if is_admin(user_id) else get_main_keyboard()
        await message.reply("🔙 Главное меню:", reply_markup=keyboard)
        return
    
    if text == "🔙 Назад к играм":
        keyboard = get_games_keyboard()
        if keyboard:
            await message.reply("🎮 Выбери игру:", reply_markup=keyboard)
        else:
            await message.reply("📭 Пока нет доступных игр.", reply_markup=get_main_keyboard())
        return
    
    # --- ПОЛЬЗОВАТЕЛЬСКИЕ КНОПКИ ---
    
    if text == "🎮 Игры":
        keyboard = get_games_keyboard()
        if keyboard:
            await message.reply("🎮 **Доступные игры:**\n\nВыбери игру, чтобы увидеть читы:", reply_markup=keyboard)
        else:
            await message.reply("📭 Пока нет доступных читов.", reply_markup=get_main_keyboard())
        return
    
    elif text == "👤 Профиль":
        user_data = db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        invites = user_data['total_invites'] if user_data else 0
        created = user_data['created_at'] if user_data else "?"
        
        await message.reply(
            f"👤 **Твой профиль**\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"👥 Приглашений: {invites}\n"
            f"📅 Регистрация: {created}\n\n"
            f"🔗 Приглашай друзей и получай больше читов!",
            reply_markup=get_main_keyboard()
        )
        return
    
    elif text == "🔗 Рефералка":
        bot_username = (await app.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        await message.reply(
            f"🔗 **Твоя реферальная ссылка:**\n\n"
            f"`{ref_link}`\n\n"
            f"📢 Отправь эту ссылку друзьям!\n"
            f"За каждого приглашенного ты получаешь +1 к счету.",
            reply_markup=get_main_keyboard()
        )
        return
    
    elif text == "❓ Помощь":
        await message.reply(
            f"📋 **Как пользоваться ботом:**\n\n"
            f"1️⃣ Нажми «🎮 Игры»\n"
            f"2️⃣ Выбери игру из списка\n"
            f"3️⃣ Нажми на название чита\n"
            f"4️⃣ Файл автоматически отправится\n\n"
            f"🔗 **Реферальная система:**\n"
            f"• Отправляй свою ссылку друзьям\n"
            f"• За каждого приглашенного получаешь +1\n"
            f"• Чем больше приглашений — тем больше читов!\n\n"
            f"📌 Для админов есть дополнительные команды.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # --- ВЫБОР ИГРЫ ---
    if text.startswith("🎮 "):
        game = text[3:]  # Убираем "🎮 "
        keyboard = get_cheats_keyboard(game)
        
        if keyboard:
            await message.reply(f"🎮 **{game}**\n\nВыбери чит:", reply_markup=keyboard)
        else:
            await message.reply(f"❌ Для игры {game} пока нет читов.", reply_markup=get_games_keyboard())
        return
    
    # --- ВЫБОР ЧИТА ---
    if text.startswith("📄 "):
        cheat_name = text[3:]  # Убираем "📄 "
        
        # Ищем файл по названию
        file_data = db.fetch_one("SELECT hash, remote_msg_id, name FROM files WHERE name = ?", (cheat_name,))
        
        if file_data:
            try:
                # Отправляем файл из канала-хранилища
                await client.copy_message(
                    chat_id=user_id,
                    from_chat_id=STORAGE_CHANNEL,
                    message_id=file_data['remote_msg_id']
                )
                await message.reply(f"✅ {file_data['name']} отправлен!", reply_markup=get_games_keyboard())
            except Exception as e:
                logger.error(f"Ошибка отправки файла: {e}")
                await message.reply(f"❌ Ошибка загрузки файла. Обратитесь к администратору.", reply_markup=get_games_keyboard())
        else:
            await message.reply(f"❌ Чит '{cheat_name}' не найден.", reply_markup=get_games_keyboard())
        return
    
    # --- АДМИН КНОПКИ ---
    if not is_admin(user_id):
        return
    
    if text == "📁 Добавить чит":
        waiting_for_file[user_id] = True
        await message.reply(
            "📤 **Добавление чита**\n\n"
            "1. Отправь файл (документ, видео или фото)\n"
            "2. В подписи укажи:\n"
            "`Название чита | Название игры`\n\n"
            "📌 Пример: `Aimbot | CS2`\n\n"
            "Для отмены нажми /cancel",
            reply_markup=get_admin_keyboard()
        )
        return
    
    elif text == "📋 Список читов":
        files = db.fetch_all("SELECT name, game FROM files ORDER BY game, name")
        
        if not files:
            await message.reply("📭 База читов пуста.", reply_markup=get_admin_keyboard())
            return
        
        text = "📋 **Все читы:**\n\n"
        current_game = ""
        for file in files:
            if file['game'] != current_game:
                current_game = file['game']
                text += f"\n🎮 **{current_game}**\n"
            text += f"  • {file['name']}\n"
        
        # Разбиваем на части, если текст слишком длинный
        if len(text) > 4000:
            parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for part in parts:
                await message.reply(part, reply_markup=get_admin_keyboard())
        else:
            await message.reply(text, reply_markup=get_admin_keyboard())
        return
    
    elif text == "👥 Пользователи":
        users = db.fetch_all("SELECT user_id, first_name, total_invites FROM users ORDER BY total_invites DESC")
        
        text = "👥 **Пользователи:**\n\n"
        for i, user in enumerate(users[:30], 1):
            name = user['first_name'] or str(user['user_id'])
            text += f"{i}. {name} — пригл: {user['total_invites']}\n"
        text += f"\n📊 Всего: {len(users)} пользователей"
        
        await message.reply(text, reply_markup=get_admin_keyboard())
        return
    
    elif text == "📢 Рассылка":
        waiting_for_broadcast[user_id] = True
        await message.reply(
            "📢 **Рассылка**\n\n"
            "Отправь сообщение, которое хочешь разослать всем пользователям.\n\n"
            "Для отмены нажми /cancel",
            reply_markup=get_admin_keyboard()
        )
        return
    
    elif text == "📊 Статистика":
        files_count = db.fetch_one("SELECT COUNT(*) FROM files")[0]
        users_count = db.fetch_one("SELECT COUNT(*) FROM users")[0]
        invites_total = db.fetch_one("SELECT SUM(total_invites) FROM users")[0] or 0
        
        await message.reply(
            f"📊 **Статистика бота**\n\n"
            f"📁 Читов: {files_count}\n"
            f"👥 Пользователей: {users_count}\n"
            f"🔗 Приглашений: {invites_total}\n"
            f"💾 База: SQLite\n"
            f"👑 Владелец: {OWNER_ID}",
            reply_markup=get_admin_keyboard()
        )
        return
    
    elif text == "🧹 Очистка":
        # Удаляем неактивных пользователей (30 дней)
        cursor = db.execute("""
            DELETE FROM users 
            WHERE julianday('now') - julianday(last_active) > 30 
            AND user_id NOT IN (SELECT user_id FROM admins)
            AND user_id != ?
        """, (OWNER_ID,))
        
        deleted = cursor.rowcount
        await message.reply(f"🧹 Удалено неактивных пользователей: {deleted}", reply_markup=get_admin_keyboard())
        return
    
    elif text == "💾 Бэкап":
        if os.path.exists(DB_PATH):
            await message.reply_document(DB_PATH, caption=f"📦 Бэкап базы данных от {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        else:
            await message.reply("❌ Файл базы не найден")
        return


# --- ЗАГРУЗКА ФАЙЛОВ ---
waiting_for_file = {}

@app.on_message((filters.document | filters.video | filters.photo) & filters.private)
async def handle_file_upload(client, message):
    user_id = message.from_user.id
    
    # Проверяем, ожидаем ли мы файл
    if not waiting_for_file.get(user_id, False):
        return
    
    # Проверяем права админа
    if not is_admin(user_id):
        waiting_for_file[user_id] = False
        await message.reply("⛔ У вас нет прав на загрузку файлов!")
        return
    
    status = await message.reply("⏳ Сохраняю чит...")
    
    try:
        # Копируем в канал-хранилище
        sent = await message.copy(STORAGE_CHANNEL)
        
        # Генерируем уникальный хеш
        file_hash = secrets.token_urlsafe(8)
        
        # Определяем тип файла
        if message.document:
            file_type = "doc"
            default_name = message.document.file_name or "document"
        elif message.video:
            file_type = "video"
            default_name = message.video.file_name or "video"
        else:
            file_type = "photo"
            default_name = "photo"
        
        # Парсим название и игру из подписи
        name = default_name
        game = "Без игры"
        
        if message.caption:
            if "|" in message.caption:
                parts = message.caption.split("|")
                name = parts[0].strip()
                game = parts[1].strip()
            else:
                name = message.caption.strip()
        
        # Сохраняем в базу
        db.execute(
            "INSERT INTO files (hash, remote_msg_id, type, name, game, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (file_hash, sent.id, file_type, name, game, user_id)
        )
        
        bot = await app.get_me()
        
        await status.edit_text(
            f"✅ **Чит успешно добавлен!**\n\n"
            f"📄 Название: {name}\n"
            f"🎮 Игра: {game}\n"
            f"🔗 Ссылка: `https://t.me/{bot.username}?start={file_hash}`"
        )
        
        waiting_for_file[user_id] = False
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await status.edit_text(f"❌ Ошибка сохранения: {str(e)}")
        waiting_for_file[user_id] = False


# --- РАССЫЛКА ---
waiting_for_broadcast = {}

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client, message):
    user_id = message.from_user.id
    
    if waiting_for_file.get(user_id):
        waiting_for_file[user_id] = False
        await message.reply("✅ Загрузка отменена")
    elif waiting_for_broadcast.get(user_id):
        waiting_for_broadcast[user_id] = False
        await message.reply("✅ Рассылка отменена")
    else:
        await message.reply("❌ Нет активных операций")


@app.on_message(filters.text & filters.private)
async def handle_broadcast_message(client, message):
    user_id = message.from_user.id
    
    # Проверяем, ожидаем ли мы сообщение для рассылки
    if not waiting_for_broadcast.get(user_id, False):
        return
    
    # Проверяем права админа
    if not is_admin(user_id):
        waiting_for_broadcast[user_id] = False
        return
    
    waiting_for_broadcast[user_id] = False
    
    # Получаем всех пользователей
    users = db.fetch_all("SELECT user_id FROM users")
    if not users:
        await message.reply("❌ Нет пользователей для рассылки")
        return
    
    status = await message.reply(f"🚀 Начинаю рассылку на {len(users)} пользователей...")
    
    sent = 0
    failed = 0
    
    for i, user in enumerate(users):
        try:
            await message.copy(user['user_id'])
            sent += 1
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed to {user['user_id']}: {e}")
        
        # Обновляем статус каждые 10 сообщений
        if (i + 1) % 10 == 0:
            await status.edit_text(f"📨 Прогресс: {sent + failed}/{len(users)}\n✅ Успешно: {sent}\n❌ Ошибок: {failed}")
            await asyncio.sleep(0.5)
    
    await status.edit_text(f"✅ **Рассылка завершена!**\n\n✅ Успешно: {sent}\n❌ Ошибок: {failed}")


# --- ВОССТАНОВЛЕНИЕ БАЗЫ ---
waiting_for_backup = {}

@app.on_message(filters.command("restore") & filters.user(OWNER_ID))
async def restore_command(client, message):
    waiting_for_backup[message.from_user.id] = True
    await message.reply("📤 **Восстановление базы**\n\nПришли файл `files.db` для восстановления.")


@app.on_message(filters.document & filters.user(OWNER_ID))
async def handle_restore_file(client, message):
    user_id = message.from_user.id
    
    if not waiting_for_backup.get(user_id, False):
        return
    
    if "files.db" not in message.document.file_name:
        return
    
    status = await message.reply("⏳ Восстановление базы данных...")
    
    try:
        temp_path = "temp_restore.db"
        await message.download(file_name=temp_path)
        
        # Проверяем структуру
        check_conn = sqlite3.connect(temp_path)
        check_conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, remote_msg_id INTEGER, type TEXT, name TEXT, game TEXT)")
        check_conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        
        files_count = check_conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        users_count = check_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        check_conn.close()
        
        # Заменяем базу
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        shutil.move(temp_path, DB_PATH)
        
        # Пересоздаем подключение
        global db
        db.conn.close()
        db._init_db()
        
        waiting_for_backup[user_id] = False
        await status.edit_text(f"✅ **База восстановлена!**\n\n📁 Файлов: {files_count}\n👥 Пользователей: {users_count}")
        
    except Exception as e:
        await status.edit_text(f"❌ Ошибка восстановления: {str(e)}")


# --- ЗАПУСК ---
if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    logger.info(f"👑 Владелец: {OWNER_ID}")
    app.run()
