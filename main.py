import os
import sqlite3
import secrets
import asyncio
import shutil
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional, Tuple, List, Dict
from enum import Enum

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, Message
)
from pyrogram.errors import UserNotParticipant, FloodWait, PeerIdInvalid

# --- НАСТРОЙКИ ---
API_ID = int(os.environ.get("API_ID", 39522849))
API_HASH = os.environ.get("API_HASH", "26909eddad0be2400fb765fad0e267f8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw")
OWNER_ID = int(os.environ.get("OWNER_ID", 1471307057))
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/OfficialPlutonium")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@OfficialPlutonium")
STORAGE_CHANNEL = os.environ.get("STORAGE_CHANNEL", "@IllyaTelegram")

DB_PATH = "files.db"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- ПРАВА ДОСТУПА ---
class AdminLevel(Enum):
    OWNER = 0
    SUPER_ADMIN = 1
    ADMIN = 2
    MODER = 3

class AdminPermissions:
    PERMISSIONS = {
        'upload_files': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN, AdminLevel.ADMIN],
        'delete_files': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN],
        'send_broadcast': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN, AdminLevel.ADMIN],
        'manage_admins': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN],
        'view_stats': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN, AdminLevel.ADMIN, AdminLevel.MODER],
        'ban_users': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN, AdminLevel.MODER],
        'view_users': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN, AdminLevel.ADMIN, AdminLevel.MODER],
        'op_system': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN],
        'categories': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN, AdminLevel.ADMIN],
        'view_files': [AdminLevel.OWNER, AdminLevel.SUPER_ADMIN, AdminLevel.ADMIN, AdminLevel.MODER],
    }
    
    @staticmethod
    def has_permission(admin_level: AdminLevel, permission: str) -> bool:
        return admin_level in AdminPermissions.PERMISSIONS.get(permission, [])


# --- МЕНЕДЖЕР БАЗЫ ДАННЫХ ---
class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._initialized = False
        
    @contextmanager
    def get_cursor(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def init_db(self):
        if self._initialized:
            return
            
        with self.get_cursor() as cursor:
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    op_level INTEGER DEFAULT 0,
                    invited_by INTEGER DEFAULT 0,
                    total_invites INTEGER DEFAULT 0,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned BOOLEAN DEFAULT FALSE,
                    ban_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица файлов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    hash TEXT PRIMARY KEY,
                    remote_msg_id INTEGER,
                    type TEXT,
                    name TEXT,
                    category TEXT,
                    created_by INTEGER,
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
                    level INTEGER DEFAULT 3,
                    added_by INTEGER,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица категорий
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    name TEXT PRIMARY KEY,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица логов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица рассылок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_text TEXT,
                    message_id INTEGER,
                    sent_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
            """)
            
            # Добавляем владельца в админы
            self._add_owner(cursor)
            
            # Добавляем категории по умолчанию
            self._add_default_categories(cursor)
            
        self._initialized = True
        logger.info("✅ База данных SQLite готова")
    
    def _add_owner(self, cursor):
        cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (OWNER_ID,))
        exists = cursor.fetchone()
        if not exists:
            cursor.execute("INSERT INTO admins (user_id, level, added_by) VALUES (?, ?, ?)", 
                          (OWNER_ID, 0, OWNER_ID))
            logger.info(f"👑 Владелец {OWNER_ID} добавлен")
    
    def _add_default_categories(self, cursor):
        default_cats = ["Российские", "Зарубежные", "Документальное", "Аниме", "Сериалы", "Фильмы"]
        for cat in default_cats:
            cursor.execute("SELECT name FROM categories WHERE name = ?", (cat,))
            exists = cursor.fetchone()
            if not exists:
                cursor.execute("INSERT INTO categories (name, created_by) VALUES (?, ?)", (cat, OWNER_ID))
    
    def log_action(self, user_id: int, action: str, details: str = None):
        with self.get_cursor() as cursor:
            cursor.execute("INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)", 
                          (user_id, action, details))
    
    # --- ПОЛЬЗОВАТЕЛИ ---
    def save_user(self, user_id: int, username: str = None, first_name: str = None, 
                  last_name: str = None, inviter_id: int = None):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute("""
                    UPDATE users SET 
                        username = ?, first_name = ?, last_name = ?, last_active = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (username, first_name, last_name, user_id))
            else:
                cursor.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name, invited_by) 
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, username, first_name, last_name, inviter_id or 0))
                
                if inviter_id and inviter_id != user_id:
                    cursor.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter_id,))
                    cursor.execute("INSERT INTO invites (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user_id))
                    self._update_op_levels(cursor)
    
    def _update_op_levels(self, cursor):
        cursor.execute("""
            UPDATE users SET op_level = CASE
                WHEN total_invites >= 20 THEN 5
                WHEN total_invites >= 10 THEN 4
                WHEN total_invites >= 5 THEN 3
                WHEN total_invites >= 3 THEN 2
                WHEN total_invites >= 1 THEN 1
                ELSE 0
            END
        """)
    
    def get_user(self, user_id: int):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            return cursor.fetchone()
    
    def get_all_users(self, include_banned: bool = False):
        with self.get_cursor() as cursor:
            if include_banned:
                cursor.execute("SELECT user_id FROM users")
            else:
                cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
            return cursor.fetchall()
    
    def get_active_users(self, days: int = 7):
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT user_id FROM users 
                WHERE julianday('now') - julianday(last_active) <= ? AND is_banned = 0
            """, (days,))
            return cursor.fetchall()
    
    def get_top_inviters(self, limit: int = 10):
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT user_id, username, first_name, total_invites, op_level
                FROM users WHERE total_invites > 0 
                ORDER BY total_invites DESC, op_level DESC LIMIT ?
            """, (limit,))
            return cursor.fetchall()
    
    def ban_user(self, user_id: int, reason: str = None, admin_id: int = None):
        with self.get_cursor() as cursor:
            cursor.execute("UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?", (reason, user_id))
            if admin_id:
                self.log_action(admin_id, "ban_user", f"Banned {user_id}: {reason}")
    
    def unban_user(self, user_id: int, admin_id: int = None):
        with self.get_cursor() as cursor:
            cursor.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?", (user_id,))
            if admin_id:
                self.log_action(admin_id, "unban_user", f"Unbanned {user_id}")
    
    def cleanup_inactive_users(self, days: int = 30, admin_id: int = None):
        with self.get_cursor() as cursor:
            cursor.execute("""
                DELETE FROM users 
                WHERE julianday('now') - julianday(last_active) > ? AND op_level = 0 AND is_banned = 0
            """, (days,))
            deleted = cursor.rowcount
            if admin_id and deleted > 0:
                self.log_action(admin_id, "cleanup", f"Deleted {deleted} inactive users")
            return deleted
    
    # --- АДМИНЫ ---
    def get_admin_level(self, user_id: int) -> Optional[AdminLevel]:
        with self.get_cursor() as cursor:
            cursor.execute("SELECT level FROM admins WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            if result:
                return AdminLevel(result[0])
            return None
    
    def add_admin(self, user_id: int, level: AdminLevel, added_by: int):
        with self.get_cursor() as cursor:
            cursor.execute("INSERT OR REPLACE INTO admins (user_id, level, added_by) VALUES (?, ?, ?)",
                          (user_id, level.value, added_by))
            self.log_action(added_by, "add_admin", f"Added admin {user_id} with level {level.value}")
    
    def remove_admin(self, user_id: int, removed_by: int = None):
        with self.get_cursor() as cursor:
            cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            if removed_by:
                self.log_action(removed_by, "remove_admin", f"Removed admin {user_id}")
    
    def get_all_admins(self):
        with self.get_cursor() as cursor:
            cursor.execute("""
                SELECT a.*, u.username, u.first_name, u.last_name, u.op_level
                FROM admins a LEFT JOIN users u ON a.user_id = u.user_id 
                ORDER BY a.level ASC
            """)
            return cursor.fetchall()
    
    # --- ФАЙЛЫ ---
    def save_file(self, file_hash: str, remote_msg_id: int, file_type: str, 
                  name: str, created_by: int, category: str = None):
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO files (hash, remote_msg_id, type, name, category, created_by) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (file_hash, remote_msg_id, file_type, name, category, created_by))
            self.log_action(created_by, "upload_file", f"Uploaded: {name}")
    
    def get_file(self, file_hash: str):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM files WHERE hash = ?", (file_hash,))
            return cursor.fetchone()
    
    def get_all_files(self, category: str = None):
        with self.get_cursor() as cursor:
            if category:
                cursor.execute("SELECT hash, name, category FROM files WHERE category = ? ORDER BY created_at DESC", (category,))
            else:
                cursor.execute("SELECT hash, name, category FROM files ORDER BY created_at DESC")
            return cursor.fetchall()
    
    def delete_file(self, file_hash: str, admin_id: int = None):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT name FROM files WHERE hash = ?", (file_hash,))
            file = cursor.fetchone()
            cursor.execute("DELETE FROM files WHERE hash = ?", (file_hash,))
            if admin_id and file:
                self.log_action(admin_id, "delete_file", f"Deleted: {file[0]}")
            return cursor.rowcount
    
    def get_files_count_by_category(self):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT category, COUNT(*) as count FROM files GROUP BY category")
            return cursor.fetchall()
    
    # --- КАТЕГОРИИ ---
    def add_category(self, name: str, created_by: int):
        with self.get_cursor() as cursor:
            cursor.execute("INSERT OR IGNORE INTO categories (name, created_by) VALUES (?, ?)", (name, created_by))
            self.log_action(created_by, "add_category", f"Added category: {name}")
    
    def get_categories(self):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT name FROM categories ORDER BY name")
            return cursor.fetchall()
    
    def delete_category(self, name: str, admin_id: int = None):
        with self.get_cursor() as cursor:
            cursor.execute("DELETE FROM categories WHERE name = ?", (name,))
            if admin_id:
                self.log_action(admin_id, "delete_category", f"Deleted category: {name}")
    
    # --- СТАТИСТИКА ---
    def get_stats(self):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM files")
            files_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
            users_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
            banned_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE op_level > 0")
            op_users_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM admins")
            admins_count = cursor.fetchone()[0]
            
            return {
                'files': files_count,
                'users': users_count,
                'banned': banned_count,
                'admins': admins_count,
                'op_users': op_users_count
            }
    
    # --- РАССЫЛКИ ---
    def save_broadcast(self, message_text: str, message_id: int, created_by: int):
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO broadcasts (message_text, message_id, created_by) VALUES (?, ?, ?)
            """, (message_text, message_id, created_by))
            return cursor.lastrowid
    
    def update_broadcast_stats(self, broadcast_id: int, sent: int, failed: int):
        with self.get_cursor() as cursor:
            cursor.execute("""
                UPDATE broadcasts SET sent_count = sent_count + ?, failed_count = failed_count + ? WHERE id = ?
            """, (sent, failed, broadcast_id))
    
    def finish_broadcast(self, broadcast_id: int):
        with self.get_cursor() as cursor:
            cursor.execute("UPDATE broadcasts SET status = 'completed' WHERE id = ?", (broadcast_id,))
    
    def get_broadcasts(self, limit: int = 10):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT ?", (limit,))
            return cursor.fetchall()


# --- ИНИЦИАЛИЗАЦИЯ ---
db = DatabaseManager()
db.init_db()

app = Client("plutonium_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Временные данные
waiting_for_backup = {}
waiting_for_file = {}
waiting_for_broadcast = {}


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def check_sub(client, user_id):
    try:
        await client.get_chat_member(CHANNEL_ID, user_id)
        return True
    except UserNotParticipant:
        return False
    except:
        return True


async def check_ban(user_id: int) -> Tuple[bool, str]:
    user = db.get_user(user_id)
    if user:
        return user['is_banned'], user['ban_reason']
    return False, None


async def check_permission(user_id: int, permission: str) -> bool:
    if user_id == OWNER_ID:
        return True
    admin_level = db.get_admin_level(user_id)
    if admin_level is None:
        return False
    return AdminPermissions.has_permission(admin_level, permission)


# --- КЛАВИАТУРЫ ---
def get_main_menu(user_id: int):
    buttons = [
        [InlineKeyboardButton("📚 Категории", callback_data="menu_categories")],
        [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"),
         InlineKeyboardButton("⭐ Мой OP", callback_data="menu_op")]
    ]
    if db.get_admin_level(user_id) is not None:
        buttons.append([InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)


def get_admin_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Файлы", callback_data="admin_files"),
         InlineKeyboardButton("🏷️ Категории", callback_data="admin_categories")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
         InlineKeyboardButton("⭐ OP Система", callback_data="admin_op")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
         InlineKeyboardButton("🚫 Бан/Разбан", callback_data="admin_ban")],
        [InlineKeyboardButton("👑 Управление админами", callback_data="admin_admins"),
         InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🧹 Очистка неактивных", callback_data="admin_cleanup"),
         InlineKeyboardButton("📋 Список файлов", callback_data="admin_file_list")],
        [InlineKeyboardButton("➕ Добавить файл", callback_data="admin_add_file"),
         InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")]
    ])


def get_categories_keyboard():
    categories = db.get_categories()
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(f"📁 {cat[0]}", callback_data=f"category_{cat[0]}")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)


def get_files_list_keyboard(category: str = None, page: int = 0, items_per_page: int = 10):
    files = db.get_all_files(category)
    total = len(files)
    start = page * items_per_page
    end = start + items_per_page
    current_files = files[start:end]
    
    buttons = []
    for file in current_files:
        name = file[1][:30]
        hash_val = file[0]
        buttons.append([InlineKeyboardButton(f"📄 {name}", callback_data=f"file_{hash_val}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"files_page_{page-1}_{category or ''}"))
    if end < total:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"files_page_{page+1}_{category or ''}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_files" if category else "back_main")])
    
    return InlineKeyboardMarkup(buttons), total


def get_users_list_keyboard(page: int = 0, items_per_page: int = 10):
    users = db.get_all_users()
    total = len(users)
    start = page * items_per_page
    end = start + items_per_page
    current_users = users[start:end]
    
    buttons = []
    for user in current_users:
        user_id = user[0]
        user_data = db.get_user(user_id)
        name = user_data['first_name'] or user_data['username'] or str(user_id)
        buttons.append([InlineKeyboardButton(f"👤 {name[:20]}", callback_data=f"user_{user_id}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"users_page_{page-1}"))
    if end < total:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"users_page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons), total


def get_admins_list_keyboard():
    admins = db.get_all_admins()
    buttons = []
    for admin in admins:
        user_id = admin['user_id']
        name = admin['first_name'] or admin['username'] or str(user_id)
        level_name = ["👑 Владелец", "⭐ СуперАдмин", "🛡️ Админ", "🔰 Модер"][admin['level']]
        buttons.append([InlineKeyboardButton(f"{level_name} {name}", callback_data=f"admin_{user_id}")])
    
    buttons.append([InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add_new")])
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(buttons)


# --- ОБРАБОТЧИКИ КОМАНД ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user = message.from_user
    inviter_id = None
    
    if len(message.command) > 1:
        ref_code = message.command[1]
        if ref_code.startswith("ref_"):
            try:
                inviter_id = int(ref_code.split("_")[1])
                if inviter_id == user.id:
                    inviter_id = None
            except:
                pass
    
    db.save_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        inviter_id=inviter_id
    )
    
    is_banned, ban_reason = await check_ban(user.id)
    if is_banned:
        reason_text = f"\nПричина: {ban_reason}" if ban_reason else ""
        return await message.reply(f"⛔ **Вы забанены!**{reason_text}")
    
    if not await check_sub(client, user.id):
        sub_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться", url=CHANNEL_URL)]])
        return await message.reply(f"👋 Привет! Подпишись на канал.", reply_markup=sub_kb)
    
    user_data = db.get_user(user.id)
    op_level = user_data['op_level']
    invites = user_data['total_invites']
    
    await message.reply(
        f"👋 **Добро пожаловать, {user.first_name}!**\n\n"
        f"📁 Архив Plutonium\n"
        f"⭐ OP уровень: {op_level}\n"
        f"👥 Приглашений: {invites}\n\n"
        f"Приглашай друзей для повышения OP уровня!",
        reply_markup=get_main_menu(user.id)
    )


@app.on_callback_query()
async def handle_callbacks(client, callback: CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    
    # --- ГЛАВНОЕ МЕНЮ ---
    if data == "back_main":
        user_data = db.get_user(user_id)
        op_level = user_data['op_level']
        invites = user_data['total_invites']
        await callback.message.edit_text(
            f"👋 **Главное меню**\n\n⭐ OP: {op_level} | 👥 Пригл: {invites}",
            reply_markup=get_main_menu(user_id)
        )
    
    elif data == "menu_categories":
        await callback.message.edit_text(
            "📚 **Выберите категорию:**",
            reply_markup=get_categories_keyboard()
        )
    
    elif data.startswith("category_"):
        cat_name = data.split("_", 1)[1]
        keyboard, total = get_files_list_keyboard(cat_name, 0)
        await callback.message.edit_text(
            f"📁 **Категория: {cat_name}**\nВсего файлов: {total}",
            reply_markup=keyboard
        )
    
    elif data.startswith("files_page_"):
        parts = data.split("_")
        page = int(parts[2])
        cat = parts[3] if len(parts) > 3 and parts[3] else None
        keyboard, total = get_files_list_keyboard(cat, page)
        await callback.message.edit_text(
            f"📁 **Список файлов**\nВсего: {total}",
            reply_markup=keyboard
        )
    
    elif data.startswith("file_"):
        file_hash = data.split("_", 1)[1]
        file_data = db.get_file(file_hash)
        if file_data:
            remote_msg_id = file_data['remote_msg_id']
            name = file_data['name']
            await callback.answer(f"Загрузка: {name}")
            await client.copy_message(user_id, STORAGE_CHANNEL, remote_msg_id)
    
    elif data == "menu_profile":
        user_data = db.get_user(user_id)
        op_level = user_data['op_level']
        invites = user_data['total_invites']
        created_at = user_data['created_at']
        
        ref_link = f"https://t.me/{app.me().username}?start=ref_{user_id}"
        
        await callback.message.edit_text(
            f"👤 **Ваш профиль**\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"⭐ OP уровень: {op_level}\n"
            f"👥 Приглашений: {invites}\n"
            f"📅 Регистрация: {created_at}\n\n"
            f"🔗 **Реферальная ссылка:**\n`{ref_link}`\n\n"
            f"Приглашай друзей и повышай OP уровень!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_main")]])
        )
    
    elif data == "menu_op":
        user_data = db.get_user(user_id)
        op_level = user_data['op_level']
        invites = user_data['total_invites']
        
        levels_text = {
            0: "🔴 Обычный",
            1: "🟡 Бронза (1+ пригл)",
            2: "🟠 Серебро (3+ пригл)",
            3: "🟢 Золото (5+ пригл)",
            4: "🔵 Платина (10+ пригл)",
            5: "💎 Алмаз (20+ пригл)"
        }
        
        next_level = ""
        if op_level == 0:
            next_level = "\n\n🎯 До следующего уровня: +1 приглашение"
        elif op_level == 1:
            next_level = "\n\n🎯 До следующего уровня: +2 приглашения"
        elif op_level == 2:
            next_level = "\n\n🎯 До следующего уровня: +2 приглашения"
        elif op_level == 3:
            next_level = "\n\n🎯 До следующего уровня: +5 приглашений"
        elif op_level == 4:
            next_level = "\n\n🎯 До следующего уровня: +10 приглашений"
        
        await callback.message.edit_text(
            f"⭐ **Ваш OP статус**\n\n"
            f"Текущий уровень: {levels_text.get(op_level, 'Обычный')}\n"
            f"Всего приглашений: {invites}{next_level}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_main")]])
        )
    
    # --- АДМИН ПАНЕЛЬ ---
    elif data == "admin_panel":
        if not await check_permission(user_id, 'view_stats'):
            return await callback.answer("⛔ Нет доступа", show_alert=True)
        await callback.message.edit_text(
            "👑 **Панель администратора**\n\nВыберите раздел:",
            reply_markup=get_admin_panel()
        )
    
    elif data == "admin_stats":
        stats = db.get_stats()
        await callback.message.edit_text(
            f"📊 **Статистика бота**\n\n"
            f"📁 Файлов: `{stats['files']}`\n"
            f"👥 Пользователей: `{stats['users']}`\n"
            f"⭐ OP пользователей: `{stats['op_users']}`\n"
            f"⛔ Забанено: `{stats['banned']}`\n"
            f"👑 Администраторов: `{stats['admins']}`\n"
            f"💾 База: SQLite",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
    
    elif data == "admin_files":
        keyboard, total = get_files_list_keyboard(None, 0)
        await callback.message.edit_text(
            f"📋 **Все файлы**\nВсего: {total}",
            reply_markup=keyboard
        )
    
    elif data == "admin_file_list":
        keyboard, total = get_files_list_keyboard(None, 0)
        await callback.message.edit_text(
            f"📋 **Список всех файлов**\nВсего: {total}",
            reply_markup=keyboard
        )
    
    elif data == "admin_add_file":
        if not await check_permission(user_id, 'upload_files'):
            return await callback.answer("⛔ Нет прав", show_alert=True)
        waiting_for_file[user_id] = True
        await callback.message.edit_text(
            "➕ **Добавление файла**\n\n"
            "Просто отправьте файл, документ, фото или видео\n"
            "В подписи укажите название и категорию (необязательно)\n\n"
            "Формат: `Название | Категория`\n"
            "Пример: `Интересный фильм | Фильмы`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="admin_panel")]])
        )
    
    elif data == "admin_categories":
        categories = db.get_categories()
        text = "🏷️ **Категории:**\n\n"
        for cat in categories:
            text += f"• {cat[0]}\n"
        text += "\nДля добавления используй /addcategory <название>\nДля удаления /delcategory <название>"
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
    
    elif data == "admin_users":
        keyboard, total = get_users_list_keyboard(0)
        await callback.message.edit_text(
            f"👥 **Пользователи**\nВсего: {total}",
            reply_markup=keyboard
        )
    
    elif data.startswith("users_page_"):
        page = int(data.split("_")[2])
        keyboard, total = get_users_list_keyboard(page)
        await callback.message.edit_text(
            f"👥 **Пользователи**\nВсего: {total}",
            reply_markup=keyboard
        )
    
    elif data.startswith("user_"):
        uid = int(data.split("_")[1])
        user_data = db.get_user(uid)
        if user_data:
            text = (
                f"👤 **Информация о пользователе**\n\n"
                f"🆔 ID: `{uid}`\n"
                f"👤 Имя: {user_data['first_name'] or 'Нет'}\n"
                f"📝 Username: @{user_data['username'] or 'Нет'}\n"
                f"⭐ OP уровень: {user_data['op_level']}\n"
                f"👥 Приглашений: {user_data['total_invites']}\n"
                f"📅 Регистрация: {user_data['created_at']}\n"
                f"🕐 Активен: {user_data['last_active']}\n"
                f"🚫 Забанен: {'Да' if user_data['is_banned'] else 'Нет'}"
            )
            buttons = []
            if await check_permission(user_id, 'ban_users'):
                if user_data['is_banned']:
                    buttons.append([InlineKeyboardButton("🔓 Разбанить", callback_data=f"unban_{uid}")])
                else:
                    buttons.append([InlineKeyboardButton("🔒 Забанить", callback_data=f"ban_{uid}")])
            buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_users")])
            await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    
    elif data.startswith("ban_"):
        uid = int(data.split("_")[1])
        db.ban_user(uid, "Нарушение правил", user_id)
        await callback.answer("✅ Пользователь забанен", show_alert=True)
        await callback.message.delete()
    
    elif data.startswith("unban_"):
        uid = int(data.split("_")[1])
        db.unban_user(uid, user_id)
        await callback.answer("✅ Пользователь разбанен", show_alert=True)
        await callback.message.delete()
    
    elif data == "admin_op":
        if not await check_permission(user_id, 'op_system'):
            return await callback.answer("⛔ Нет прав", show_alert=True)
        top_users = db.get_top_inviters(10)
        if not top_users:
            text = "⭐ **OP Система**\n\nПока нет пользователей с приглашениями."
        else:
            text = "⭐ **Топ приглашающих**\n\n"
            for i, user in enumerate(top_users, 1):
                name = user['first_name'] or user['username'] or str(user['user_id'])
                text += f"{i}. {name} — {user['total_invites']} пригл. (OP {user['op_level']})\n"
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
    
    elif data == "admin_admins":
        if not await check_permission(user_id, 'manage_admins'):
            return await callback.answer("⛔ Нет прав", show_alert=True)
        await callback.message.edit_text(
            "👑 **Управление админами**",
            reply_markup=get_admins_list_keyboard()
        )
    
    elif data == "admin_add_new":
        waiting_for_admin[user_id] = True
        await callback.message.edit_text(
            "➕ **Добавление администратора**\n\n"
            "Отправьте ID пользователя и уровень через пробел\n"
            "Уровни:\n"
            "1 - СуперАдмин (все права)\n"
            "2 - Админ (загрузка, рассылка)\n"
            "3 - Модер (статистика, бан)\n\n"
            "Пример: `123456789 2`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="admin_admins")]])
        )
    
    elif data.startswith("admin_"):
        try:
            uid = int(data.split("_")[1])
            admin_data = db.get_admin_level(uid)
            user_data = db.get_user(uid)
            name = user_data['first_name'] or user_data['username'] or str(uid)
            level_name = ["👑 Владелец", "⭐ СуперАдмин", "🛡️ Админ", "🔰 Модер"][admin_data.value] if admin_data else "Нет"
            
            buttons = []
            if uid != OWNER_ID and await check_permission(user_id, 'manage_admins'):
                buttons.append([InlineKeyboardButton("❌ Удалить админа", callback_data=f"remove_admin_{uid}")])
            buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_admins")])
            
            await callback.message.edit_text(
                f"👑 **Администратор**\n\n"
                f"🆔 ID: `{uid}`\n"
                f"👤 Имя: {name}\n"
                f"⭐ Уровень: {level_name}",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except:
            pass
    
    elif data.startswith("remove_admin_"):
        uid = int(data.split("_")[2])
        if uid == OWNER_ID:
            return await callback.answer("❌ Нельзя удалить владельца", show_alert=True)
        db.remove_admin(uid, user_id)
        await callback.answer("✅ Администратор удален", show_alert=True)
        await callback.message.edit_text(
            "👑 **Управление админами**",
            reply_markup=get_admins_list_keyboard()
        )
    
    elif data == "admin_broadcast":
        if not await check_permission(user_id, 'send_broadcast'):
            return await callback.answer("⛔ Нет прав", show_alert=True)
        waiting_for_broadcast[user_id] = True
        await callback.message.edit_text(
            "📢 **Рассылка**\n\n"
            "Отправьте сообщение, которое хотите разослать\n"
            "Можно использовать форматирование (жирный, курсив и т.д.)\n\n"
            "Для отмены отправьте /cancel",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Отмена", callback_data="admin_panel")]])
        )
    
    elif data == "admin_cleanup":
        if not await check_permission(user_id, 'ban_users'):
            return await callback.answer("⛔ Нет прав", show_alert=True)
        deleted = db.cleanup_inactive_users(30, user_id)
        await callback.message.edit_text(
            f"🧹 **Очистка неактивных пользователей**\n\n"
            f"Удалено пользователей, неактивных более 30 дней: `{deleted}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
    
    elif data == "admin_close":
        await callback.message.delete()


# --- ОБРАБОТЧИКИ ДЛЯ ЗАГРУЗКИ ФАЙЛОВ ---
@app.on_message((filters.document | filters.video | filters.photo) & filters.private)
async def handle_upload(client, message):
    user_id = message.from_user.id
    
    if not waiting_for_file.get(user_id, False):
        return
    
    if not await check_permission(user_id, 'upload_files'):
        waiting_for_file[user_id] = False
        return await message.reply("⛔ У вас нет прав на загрузку файлов!")
    
    status = await message.reply("⏳ Сохраняю файл...")
    
    try:
        sent = await message.copy(STORAGE_CHANNEL)
        file_hash = secrets.token_urlsafe(8)
        
        if message.document:
            file_type = "doc"
            name = message.document.file_name
        elif message.video:
            file_type = "video"
            name = message.video.file_name or "Видео"
        else:
            file_type = "photo"
            name = "Фото"
        
        category = None
        if message.caption:
            if "|" in message.caption:
                parts = message.caption.split("|")
                name = parts[0].strip()
                category = parts[1].strip()
            else:
                name = message.caption.strip()
        
        db.save_file(file_hash, sent.id, file_type, name, user_id, category)
        
        bot_username = (await app.me()).username
        
        await status.edit_text(
            f"✅ **Файл сохранен!**\n\n"
            f"📄 Название: {name}\n"
            f"🏷️ Категория: {category or 'Без категории'}\n"
            f"🔗 Ссылка: `https://t.me/{bot_username}?start={file_hash}`"
        )
        
        waiting_for_file[user_id] = False
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await status.edit_text(f"❌ Ошибка сохранения: {e}")
        waiting_for_file[user_id] = False


# --- ОБРАБОТЧИК ДЛЯ ДОБАВЛЕНИЯ АДМИНОВ ---
waiting_for_admin = {}

@app.on_message(filters.command("addadmin") & filters.private)
async def add_admin_cmd(client, message):
    user_id = message.from_user.id
    if not await check_permission(user_id, 'manage_admins'):
        return await message.reply("⛔ Нет прав")
    
    try:
        args = message.text.split()
        if len(args) < 3:
            return await message.reply("Использование: /addadmin user_id уровень\nУровни: 1-СуперАдмин, 2-Админ, 3-Модер")
        
        target_id = int(args[1])
        level = int(args[2])
        
        if target_id == OWNER_ID:
            return await message.reply("❌ Это владелец")
        
        if level not in [1, 2, 3]:
            return await message.reply("❌ Уровень должен быть 1, 2 или 3")
        
        db.add_admin(target_id, AdminLevel(level), user_id)
        await message.reply(f"✅ Пользователь добавлен как администратор уровня {level}")
        
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


# --- ОБРАБОТЧИК ДЛЯ КАТЕГОРИЙ ---
@app.on_message(filters.command("addcategory") & filters.private)
async def add_category_cmd(client, message):
    user_id = message.from_user.id
    if not await check_permission(user_id, 'categories'):
        return await message.reply("⛔ Нет прав")
    
    try:
        args = message.text.split()
        if len(args) < 2:
            return await message.reply("Использование: /addcategory Название")
        
        cat_name = " ".join(args[1:])
        db.add_category(cat_name, user_id)
        await message.reply(f"✅ Категория '{cat_name}' добавлена")
        
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


@app.on_message(filters.command("delcategory") & filters.private)
async def delete_category_cmd(client, message):
    user_id = message.from_user.id
    if not await check_permission(user_id, 'categories'):
        return await message.reply("⛔ Нет прав")
    
    try:
        args = message.text.split()
        if len(args) < 2:
            return await message.reply("Использование: /delcategory Название")
        
        cat_name = " ".join(args[1:])
        db.delete_category(cat_name, user_id)
        await message.reply(f"✅ Категория '{cat_name}' удалена")
        
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


# --- ОБРАБОТЧИК ДЛЯ РАССЫЛКИ ---
@app.on_message(filters.command("cancel") & filters.private)
async def cancel_cmd(client, message):
    user_id = message.from_user.id
    if user_id in waiting_for_broadcast:
        del waiting_for_broadcast[user_id]
        await message.reply("✅ Рассылка отменена")
    else:
        await message.reply("Нет активной рассылки")


@app.on_message(filters.text & filters.private)
async def handle_broadcast_text(client, message):
    user_id = message.from_user.id
    
    if waiting_for_broadcast.get(user_id, False):
        del waiting_for_broadcast[user_id]
        
        users = db.get_all_users()
        if not users:
            return await message.reply("Нет пользователей для рассылки")
        
        broadcast_id = db.save_broadcast(message.text, message.id, user_id)
        
        status_msg = await message.reply(f"🚀 Начинаю рассылку на {len(users)} пользователей...")
        
        sent = 0
        failed = 0
        
        for i, user in enumerate(users):
            try:
                await message.copy(user[0])
                sent += 1
            except Exception as e:
                failed += 1
            
            if (i + 1) % 10 == 0:
                await status_msg.edit_text(f"Прогресс: {sent + failed}/{len(users)} (✅ {sent} | ❌ {failed})")
                await asyncio.sleep(0.5)
        
        db.update_broadcast_stats(broadcast_id, sent, failed)
        db.finish_broadcast(broadcast_id)
        
        await status_msg.edit_text(f"✅ Рассылка завершена!\n✅ Успешно: {sent}\n❌ Ошибок: {failed}")


# --- ОБРАБОТЧИК ДЛЯ РЕСТОРАЦИИ ---
@app.on_message(filters.command("restore") & filters.user(OWNER_ID))
async def restore_req(client, message):
    waiting_for_backup[message.from_user.id] = True
    await message.reply("📤 **Режим восстановления!**\nПришли файл `files.db`.")


@app.on_message(filters.document & filters.user(OWNER_ID))
async def handle_restore(client, message):
    user_id = message.from_user.id
    
    if user_id in waiting_for_backup and "files.db" in message.document.file_name:
        status = await message.reply("⏳ Восстановление базы...")
        try:
            temp_path = "temp_restore.db"
            await message.download(file_name=temp_path)
            
            check_conn = sqlite3.connect(temp_path)
            check_conn.execute("CREATE TABLE IF NOT EXISTS files (hash TEXT PRIMARY KEY, remote_msg_id INTEGER, type TEXT, name TEXT)")
            check_conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
            f_count = check_conn.execute("SELECT count(*) FROM files").fetchone()[0]
            u_count = check_conn.execute("SELECT count(*) FROM users").fetchone()[0]
            check_conn.close()
            
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            shutil.move(temp_path, DB_PATH)
            
            del waiting_for_backup[user_id]
            await status.edit_text(f"✅ **Успех!**\nФайлов: {f_count}\nЮзеров: {u_count}")
            
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {e}")


# --- ЗАПУСК ---
if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    logger.info(f"👑 Владелец: {OWNER_ID}")
    app.run()
   
