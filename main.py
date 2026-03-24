import os
import secrets
import asyncio
import logging
import re
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple
from enum import Enum

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery
)
from pyrogram.errors import UserNotParticipant, FloodWait

# --- ВЫБОР БАЗЫ ДАННЫХ ---
# На Railway ОБЯЗАТЕЛЬНО используем MySQL
USE_MYSQL = bool(os.environ.get("MYSQL_URL") or os.environ.get("DATABASE_URL"))

if not USE_MYSQL:
    print("⚠️ ВНИМАНИЕ! Используется SQLite. На Railway данные могут пропасть!")
    print("✅ Добавьте MySQL в Railway: New Service → Database → MySQL")
    import sqlite3
else:
    import mysql.connector

# --- НАСТРОЙКИ ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", 1471307057))
CHANNEL_URL = os.environ.get("CHANNEL_URL", "https://t.me/OfficialPlutonium")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@OfficialPlutonium")
STORAGE_CHANNEL = os.environ.get("STORAGE_CHANNEL", "@IllyaTelegram")

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
    }
    
    @staticmethod
    def has_permission(admin_level: AdminLevel, permission: str) -> bool:
        return admin_level in AdminPermissions.PERMISSIONS.get(permission, [])


# --- МЕНЕДЖЕР БАЗЫ ДАННЫХ ---
class DatabaseManager:
    def __init__(self):
        self.use_mysql = USE_MYSQL
        self.connection = None
        self._initialized = False
        
    def get_connection(self):
        if self.use_mysql:
            if self.connection is None or not self.connection.is_connected():
                self.connection = mysql.connector.connect(**self._get_mysql_config())
            return self.connection
        return sqlite3.connect("files.db", timeout=10)
    
    def _get_mysql_config(self):
        mysql_url = os.environ.get("MYSQL_URL") or os.environ.get("DATABASE_URL")
        pattern = r'mysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)'
        match = re.match(pattern, mysql_url)
        
        if match:
            return {
                'user': match.group(1),
                'password': match.group(2),
                'host': match.group(3),
                'port': int(match.group(4)),
                'database': match.group(5)
            }
        return {
            'host': os.environ.get('MYSQLHOST', 'localhost'),
            'port': int(os.environ.get('MYSQLPORT', 3306)),
            'user': os.environ.get('MYSQLUSER', 'root'),
            'password': os.environ.get('MYSQLPASSWORD', ''),
            'database': os.environ.get('MYSQLDATABASE', 'railway')
        }
    
    @contextmanager
    def get_cursor(self):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True) if self.use_mysql else conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()
            if not self.use_mysql:
                conn.close()
    
    def init_db(self):
        """Создает таблицы ТОЛЬКО если их нет - данные НЕ ЗАТИРАЮТСЯ"""
        if self._initialized:
            return
            
        with self.get_cursor() as cursor:
            # 1. Таблица пользователей
            if self.use_mysql:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username VARCHAR(100),
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        op_level INT DEFAULT 0,
                        invited_by BIGINT DEFAULT 0,
                        total_invites INT DEFAULT 0,
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_banned BOOLEAN DEFAULT FALSE,
                        ban_reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            else:
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
            
            # 2. Таблица файлов
            if self.use_mysql:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS files (
                        hash VARCHAR(50) PRIMARY KEY,
                        remote_msg_id INT,
                        type VARCHAR(20),
                        name TEXT,
                        category VARCHAR(50),
                        created_by BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_category (category),
                        INDEX idx_created_by (created_by)
                    )
                """)
            else:
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
            
            # 3. Таблица приглашений
            if self.use_mysql:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS invites (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        inviter_id BIGINT,
                        invited_id BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_inviter (inviter_id),
                        INDEX idx_invited (invited_id)
                    )
                """)
            else:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS invites (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        inviter_id INTEGER,
                        invited_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            # 4. Таблица администраторов
            if self.use_mysql:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS admins (
                        user_id BIGINT PRIMARY KEY,
                        level INT DEFAULT 3,
                        added_by BIGINT,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_level (level)
                    )
                """)
            else:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS admins (
                        user_id INTEGER PRIMARY KEY,
                        level INTEGER DEFAULT 3,
                        added_by INTEGER,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            # 5. Таблица категорий
            if self.use_mysql:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS categories (
                        name VARCHAR(50) PRIMARY KEY,
                        created_by BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            else:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS categories (
                        name TEXT PRIMARY KEY,
                        created_by INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            # 6. Таблица рассылок
            if self.use_mysql:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS broadcasts (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        message_text TEXT,
                        message_id INT,
                        sent_count INT DEFAULT 0,
                        failed_count INT DEFAULT 0,
                        created_by BIGINT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status VARCHAR(20) DEFAULT 'pending'
                    )
                """)
            else:
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
            
            # 7. Таблица логов действий
            if self.use_mysql:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT,
                        action VARCHAR(50),
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_user (user_id),
                        INDEX idx_action (action)
                    )
                """)
            else:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        action TEXT,
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            # Добавляем владельца в админы (только если его нет)
            self._add_owner_if_not_exists(cursor)
            
            # Добавляем категории по умолчанию (только если их нет)
            self._add_default_categories_if_not_exists(cursor)
            
        self._initialized = True
        logger.info(f"✅ База данных готова ({'MySQL' if self.use_mysql else 'SQLite'})")
    
    def _add_owner_if_not_exists(self, cursor):
        """Добавляет владельца в админы ТОЛЬКО если его там нет"""
        if self.use_mysql:
            cursor.execute("SELECT user_id FROM admins WHERE user_id = %s", (OWNER_ID,))
            exists = cursor.fetchone()
            if not exists:
                cursor.execute("""
                    INSERT INTO admins (user_id, level, added_by) 
                    VALUES (%s, %s, %s)
                """, (OWNER_ID, 0, OWNER_ID))
                logger.info(f"👑 Владелец {OWNER_ID} добавлен в админы")
        else:
            cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (OWNER_ID,))
            exists = cursor.fetchone()
            if not exists:
                cursor.execute("""
                    INSERT INTO admins (user_id, level, added_by) 
                    VALUES (?, ?, ?)
                """, (OWNER_ID, 0, OWNER_ID))
                logger.info(f"👑 Владелец {OWNER_ID} добавлен в админы")
    
    def _add_default_categories_if_not_exists(self, cursor):
        """Добавляет категории по умолчанию ТОЛЬКО если их нет"""
        default_cats = ["Российские", "Зарубежные", "Документальное", "Аниме", "Сериалы", "Фильмы"]
        
        for cat in default_cats:
            if self.use_mysql:
                cursor.execute("SELECT name FROM categories WHERE name = %s", (cat,))
                exists = cursor.fetchone()
                if not exists:
                    cursor.execute("INSERT INTO categories (name, created_by) VALUES (%s, %s)", (cat, OWNER_ID))
            else:
                cursor.execute("SELECT name FROM categories WHERE name = ?", (cat,))
                exists = cursor.fetchone()
                if not exists:
                    cursor.execute("INSERT INTO categories (name, created_by) VALUES (?, ?)", (cat, OWNER_ID))
    
    # --- МЕТОДЫ ДЛЯ РАБОТЫ С ДАННЫМИ ---
    
    def log_action(self, user_id: int, action: str, details: str = None):
        """Логирование действий"""
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    INSERT INTO logs (user_id, action, details) VALUES (%s, %s, %s)
                """, (user_id, action, details))
            else:
                cursor.execute("""
                    INSERT INTO logs (user_id, action, details) VALUES (?, ?, ?)
                """, (user_id, action, details))
    
    def save_user(self, user_id: int, username: str = None, first_name: str = None, 
                  last_name: str = None, inviter_id: int = None):
        """Сохранить или обновить пользователя"""
        with self.get_cursor() as cursor:
            if self.use_mysql:
                # Проверяем существование
                cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
                exists = cursor.fetchone()
                
                if exists:
                    # Обновляем существующего
                    cursor.execute("""
                        UPDATE users SET 
                            username = %s, 
                            first_name = %s, 
                            last_name = %s, 
                            last_active = CURRENT_TIMESTAMP
                        WHERE user_id = %s
                    """, (username, first_name, last_name, user_id))
                else:
                    # Создаем нового
                    cursor.execute("""
                        INSERT INTO users (user_id, username, first_name, last_name, invited_by) 
                        VALUES (%s, %s, %s, %s, %s)
                    """, (user_id, username, first_name, last_name, inviter_id or 0))
                    
                    if inviter_id and inviter_id != user_id:
                        # Увеличиваем счетчик приглашений
                        cursor.execute("""
                            UPDATE users SET total_invites = total_invites + 1 
                            WHERE user_id = %s
                        """, (inviter_id,))
                        # Записываем инвайт
                        cursor.execute("""
                            INSERT INTO invites (inviter_id, invited_id) VALUES (%s, %s)
                        """, (inviter_id, user_id))
                        # Обновляем OP уровни
                        self._update_op_levels(cursor)
            else:
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                exists = cursor.fetchone()
                
                if exists:
                    cursor.execute("""
                        UPDATE users SET 
                            username = ?, 
                            first_name = ?, 
                            last_name = ?, 
                            last_active = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    """, (username, first_name, last_name, user_id))
                else:
                    cursor.execute("""
                        INSERT INTO users (user_id, username, first_name, last_name, invited_by) 
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, username, first_name, last_name, inviter_id or 0))
                    
                    if inviter_id and inviter_id != user_id:
                        cursor.execute("""
                            UPDATE users SET total_invites = total_invites + 1 
                            WHERE user_id = ?
                        """, (inviter_id,))
                        cursor.execute("""
                            INSERT INTO invites (inviter_id, invited_id) VALUES (?, ?)
                        """, (inviter_id, user_id))
                        self._update_op_levels(cursor)
    
    def _update_op_levels(self, cursor):
        """Автообновление OP уровней"""
        if self.use_mysql:
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
        else:
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
            if self.use_mysql:
                cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            else:
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            return cursor.fetchone()
    
    def get_all_users(self, include_banned: bool = False):
        with self.get_cursor() as cursor:
            if include_banned:
                cursor.execute("SELECT user_id FROM users")
            else:
                if self.use_mysql:
                    cursor.execute("SELECT user_id FROM users WHERE is_banned = FALSE")
                else:
                    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
            return cursor.fetchall()
    
    def get_active_users(self, days: int = 7):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    SELECT user_id FROM users 
                    WHERE last_active > DATE_SUB(NOW(), INTERVAL %s DAY)
                    AND is_banned = 0
                """, (days,))
            return cursor.fetchall()
    
    def get_top_inviters(self, limit: int = 10):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    SELECT user_id, username, first_name, total_invites, op_level
                    FROM users 
                    WHERE total_invites > 0 
                    ORDER BY total_invites DESC, op_level DESC
                    LIMIT %s
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT user_id, username, first_name, total_invites, op_level
                    FROM users 
                    WHERE total_invites > 0 
                    ORDER BY total_invites DESC, op_level DESC
                    LIMIT ?
                """, (limit,))
            return cursor.fetchall()
    
    def ban_user(self, user_id: int, reason: str = None, admin_id: int = None):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    UPDATE users SET is_banned = TRUE, ban_reason = %s WHERE user_id = %s
                """, (reason, user_id))
            else:
                cursor.execute("""
                    UPDATE users SET is_banned = 1, ban_reason = ? WHERE user_id = ?
                """, (reason, user_id))
            if admin_id:
                self.log_action(admin_id, "ban_user", f"Banned {user_id}: {reason}")
    
    def unban_user(self, user_id: int, admin_id: int = None):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("UPDATE users SET is_banned = FALSE, ban_reason = NULL WHERE user_id = %s", (user_id,))
            else:
                cursor.execute("UPDATE users SET is_banned = 0, ban_reason = NULL WHERE user_id = ?", (user_id,))
            if admin_id:
                self.log_action(admin_id, "unban_user", f"Unbanned {user_id}")
    
    def cleanup_inactive_users(self, days: int = 30, admin_id: int = None):
        """Удаляет неактивных пользователей"""
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    DELETE FROM users 
                    WHERE last_active < DATE_SUB(NOW(), INTERVAL %s DAY)
                    AND op_level = 0 AND is_banned = FALSE
                """, (days,))
                deleted = cursor.rowcount
            else:
                cursor.execute("""
                    DELETE FROM users 
                    WHERE julianday('now') - julianday(last_active) > ?
                    AND op_level = 0 AND is_banned = 0
                """, (days,))
                deleted = cursor.rowcount
            
            if admin_id and deleted > 0:
                self.log_action(admin_id, "cleanup", f"Deleted {deleted} inactive users")
            return deleted
    
    # --- АДМИНЫ ---
    def get_admin_level(self, user_id: int) -> Optional[AdminLevel]:
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("SELECT level FROM admins WHERE user_id = %s", (user_id,))
                result = cursor.fetchone()
            else:
                cursor.execute("SELECT level FROM admins WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
            
            if result:
                level = result['level'] if self.use_mysql else result[0]
                return AdminLevel(level)
            return None
    
    def add_admin(self, user_id: int, level: AdminLevel, added_by: int):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    INSERT INTO admins (user_id, level, added_by) 
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE level = %s, added_by = %s
                """, (user_id, level.value, added_by, level.value, added_by))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO admins (user_id, level, added_by) 
                    VALUES (?, ?, ?)
                """, (user_id, level.value, added_by))
            self.log_action(added_by, "add_admin", f"Added admin {user_id} with level {level.value}")
    
    def remove_admin(self, user_id: int, removed_by: int = None):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("DELETE FROM admins WHERE user_id = %s", (user_id,))
            else:
                cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            if removed_by:
                self.log_action(removed_by, "remove_admin", f"Removed admin {user_id}")
    
    def get_all_admins(self):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    SELECT a.*, u.username, u.first_name, u.last_name, u.op_level
                    FROM admins a 
                    LEFT JOIN users u ON a.user_id = u.user_id 
                    ORDER BY a.level ASC
                """)
            else:
                cursor.execute("""
                    SELECT a.*, u.username, u.first_name, u.last_name, u.op_level
                    FROM admins a 
                    LEFT JOIN users u ON a.user_id = u.user_id 
                    ORDER BY a.level ASC
                """)
            return cursor.fetchall()
    
    # --- ФАЙЛЫ ---
    def save_file(self, file_hash: str, remote_msg_id: int, file_type: str, 
                  name: str, created_by: int, category: str = None):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    INSERT INTO files (hash, remote_msg_id, type, name, category, created_by) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (file_hash, remote_msg_id, file_type, name, category, created_by))
            else:
                cursor.execute("""
                    INSERT INTO files (hash, remote_msg_id, type, name, category, created_by) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (file_hash, remote_msg_id, file_type, name, category, created_by))
            self.log_action(created_by, "upload_file", f"Uploaded: {name}")
    
    def get_file(self, file_hash: str):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("SELECT * FROM files WHERE hash = %s", (file_hash,))
            else:
                cursor.execute("SELECT * FROM files WHERE hash = ?", (file_hash,))
            return cursor.fetchone()
    
    def get_all_files(self, category: str = None):
        with self.get_cursor() as cursor:
            if category:
                if self.use_mysql:
                    cursor.execute("""
                        SELECT hash, name, category FROM files 
                        WHERE category = %s ORDER BY created_at DESC
                    """, (category,))
                else:
                    cursor.execute("""
                        SELECT hash, name, category FROM files 
                        WHERE category = ? ORDER BY created_at DESC
                    """, (category,))
            else:
                cursor.execute("SELECT hash, name, category FROM files ORDER BY created_at DESC")
            return cursor.fetchall()
    
    def delete_file(self, file_hash: str, admin_id: int = None):
        with self.get_cursor() as cursor:
            # Сначала получаем имя файла для лога
            if self.use_mysql:
                cursor.execute("SELECT name FROM files WHERE hash = %s", (file_hash,))
            else:
                cursor.execute("SELECT name FROM files WHERE hash = ?", (file_hash,))
            file = cursor.fetchone()
            
            if self.use_mysql:
                cursor.execute("DELETE FROM files WHERE hash = %s", (file_hash,))
            else:
                cursor.execute("DELETE FROM files WHERE hash = ?", (file_hash,))
            
            if admin_id and file:
                name = file['name'] if self.use_mysql else file[0]
                self.log_action(admin_id, "delete_file", f"Deleted: {name}")
            return cursor.rowcount
    
    def get_files_count_by_category(self):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    SELECT category, COUNT(*) as count 
                    FROM files 
                    GROUP BY category
                """)
            else:
                cursor.execute("""
                    SELECT category, COUNT(*) as count 
                    FROM files 
                    GROUP BY category
                """)
            return cursor.fetchall()
    
    # --- КАТЕГОРИИ ---
    def add_category(self, name: str, created_by: int):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    INSERT IGNORE INTO categories (name, created_by) VALUES (%s, %s)
                """, (name, created_by))
            else:
                cursor.execute("""
                    INSERT OR IGNORE INTO categories (name, created_by) VALUES (?, ?)
                """, (name, created_by))
            self.log_action(created_by, "add_category", f"Added category: {name}")
    
    def get_categories(self):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT name FROM categories ORDER BY name")
            return cursor.fetchall()
    
    def delete_category(self, name: str, admin_id: int = None):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("DELETE FROM categories WHERE name = %s", (name,))
            else:
                cursor.execute("DELETE FROM categories WHERE name = ?", (name,))
            if admin_id:
                self.log_action(admin_id, "delete_category", f"Deleted category: {name}")
    
    # --- РАССЫЛКИ ---
    def save_broadcast(self, message_text: str, message_id: int, created_by: int):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    INSERT INTO broadcasts (message_text, message_id, created_by) 
                    VALUES (%s, %s, %s)
                """, (message_text, message_id, created_by))
                return cursor.lastrowid
            else:
                cursor.execute("""
                    INSERT INTO broadcasts (message_text, message_id, created_by) 
                    VALUES (?, ?, ?)
                """, (message_text, message_id, created_by))
                return cursor.lastrowid
    
    def update_broadcast_stats(self, broadcast_id: int, sent: int, failed: int):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    UPDATE broadcasts 
                    SET sent_count = sent_count + %s, failed_count = failed_count + %s 
                    WHERE id = %s
                """, (sent, failed, broadcast_id))
            else:
                cursor.execute("""
                    UPDATE broadcasts 
                    SET sent_count = sent_count + ?, failed_count = failed_count + ? 
                    WHERE id = ?
                """, (sent, failed, broadcast_id))
    
    def finish_broadcast(self, broadcast_id: int):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    UPDATE broadcasts SET status = 'completed' WHERE id = %s
                """, (broadcast_id,))
            else:
                cursor.execute("""
                    UPDATE broadcasts SET status = 'completed' WHERE id = ?
                """, (broadcast_id,))
    
    def get_broadcasts(self, limit: int = 10):
        with self.get_cursor() as cursor:
            if self.use_mysql:
                cursor.execute("""
                    SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT %s
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT ?
                """, (limit,))
            return cursor.fetchall()
    
    # --- СТАТИСТИКА ---
    def get_stats(self):
        with self.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM files")
            files_count = cursor.fetchone()['count'] if self.use_mysql else cursor.fetchone()[0]
            
            if self.use_mysql:
                cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_banned = FALSE")
                users_count = cursor.fetchone()['count']
                cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_banned = TRUE")
                banned_count = cursor.fetchone()['count']
                cursor.execute("SELECT COUNT(*) as count FROM users WHERE op_level > 0")
                op_users_count = cursor.fetchone()['count']
            else:
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
                users_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
                banned_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM users WHERE op_level > 0")
                op_users_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) as count FROM admins")
            admins_count = cursor.fetchone()['count'] if self.use_mysql else cursor.fetchone()[0]
            
            return {
                'files': files_count,
                'users': users_count,
                'banned': banned_count,
                'admins': admins_count,
                'op_users': op_users_count
            }


# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
db = DatabaseManager()
db.init_db()  # Таблицы создаются только если их нет, данные НЕ ТЕРЯЮТСЯ!

app = Client("plutonium_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


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
        if USE_MYSQL:
            return user['is_banned'], user['ban_reason']
        else:
            return user[8], user[9]
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
        name = cat['name'] if USE_MYSQL else cat[0]
        buttons.append([InlineKeyboardButton(f"📁 {name}", callback_data=f"category_{name}")])
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
        if USE_MYSQL:
            name = file['name'][:30]
            hash_val = file['hash']
        else:
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


# --- ОБРАБОТЧИКИ ---
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
    op_level = user_data['op_level'] if USE_MYSQL else user_data[4]
    invites = user_data['total_invites'] if USE_MYSQL else user_data[6]
    
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
        op_level = user_data['op_level'] if USE_MYSQL else user_data[4]
        invites = user_data['total_invites'] if USE_MYSQL else user_data[6]
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
            if USE_MYSQL:
                remote_msg_id = file_data['remote_msg_id']
                name = file_data['name']
            else:
                remote_msg_id = file_data[1]
                name = file_data[3]
            
            await callback.answer(f"Загрузка: {name}")
            await client.copy_message(user_id, STORAGE_CHANNEL, remote_msg_id)
    
    elif data == "menu_profile":
        user_data = db.get_user(user_id)
        if USE_MYSQL:
            op_level = user_data['op_level']
            invites = user_data['total_invites']
            created_at = user_data['created_at']
        else:
            op_level = user_data[4]
            invites = user_data[6]
            created_at = user_data[10]
        
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
        op_level = user_data['op_level'] if USE_MYSQL else user_data[4]
        invites = user_data['total_invites'] if USE_MYSQL else user_data[6]
        
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
            f"💾 База: `{DB_TYPE}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
    
    elif data == "admin_file_list":
        keyboard, total = get_files_list_keyboard(None, 0)
        await callback.message.edit_text(
            f"📋 **Список всех файлов**\nВсего: {total}",
            reply_markup=keyboard
        )
    
    elif data == "admin_add_file":
        await callback.message.edit_text(
            "➕ **Добавление файла**\n\n"
            "Просто отправьте файл, документ, фото или видео\n"
            "В подписи укажите название и категорию (необязательно)\n\n"
            "Формат: `Название | Категория`\n"
            "Пример: `Интересный фильм | Фильмы`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
        # Устанавливаем флаг ожидания файла
        waiting_for_file[user_id] = True
    
    elif data == "admin_cleanup":
        deleted = db.cleanup_inactive_users(30, user_id)
        await callback.message.edit_text(
            f"🧹 **Очистка неактивных пользователей**\n\n"
            f"Удалено пользователей, неактивных более 30 дней: `{deleted}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
    
    elif data == "admin_close":
        await callback.message.delete()


# --- ЗАГРУЗКА ФАЙЛОВ АДМИНАМИ ---
waiting_for_file = {}

@app.on_message((filters.document | filters.video | filters.photo) & filters.private)
async def handle_upload(client, message):
    user_id = message.from_user.id
    
    # Проверяем, ожидаем ли мы файл от админа
    if not waiting_for_file.get(user_id, False):
        return
    
    if not await check_permission(user_id, 'upload_files'):
        waiting_for_file[user_id] = False
        return await message.reply("⛔ У вас нет прав на загрузку файлов!")
    
    status = await message.reply("⏳ Сохраняю файл...")
    
    try:
        # Копируем в хранилище
        sent = await message.copy(STORAGE_CHANNEL)
        
        # Генерируем хеш
        file_hash = secrets.token_urlsafe(8)
        
        # Определяем тип
        if message.document:
            file_type = "doc"
            name = message.document.file_name
        elif message.video:
            file_type = "video"
            name = message.video.file_name or "Видео"
        else:
            file_type = "photo"
            name = "Фото"
        
        # Парсим категорию из подписи
        category = None
        if message.caption:
            parts = message.caption.split("|")
            if len(parts) >= 2:
                name = parts[0].strip()
                category = parts[1].strip()
            else:
                name = message.caption.strip()
        
        # Сохраняем в БД
        db.save_file(file_hash, sent.id, file_type, name, user_id, category)
        
        await status.edit_text(
            f"✅ **Файл сохранен!**\n\n"
            f"📄 Название: {name}\n"
            f"🏷️ Категория: {category or 'Без категории'}\n"
            f"🔗 Ссылка: `https://t.me/{app.me().username}?start={file_hash}`"
        )
        
        waiting_for_file[user_id] = False
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await status.edit_text(f"❌ Ошибка сохранения: {e}")
        waiting_for_file[user_id] = False


# --- ЗАПУСК ---
if __name__ == "__main__":
    logger.info(f"🚀 Бот запущен с БД: {DB_TYPE}")
    logger.info(f"👑 Владелец: {OWNER_ID}")
    app.run()
