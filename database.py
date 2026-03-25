import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional, List, Any
from config import Config

logger = logging.getLogger(__name__)

class Database:
    """Работа с базой данных"""
    
    def __init__(self):
        self.db_path = Config.DB_PATH
        self._conn = None
        self._init_db()
    
    def _get_conn(self):
        """Получить соединение с БД"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn
    
    def _init_db(self):
        """Создание таблиц"""
        with self._get_conn() as conn:
            # Таблица пользователей
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    invited_by INTEGER DEFAULT 0,
                    total_invites INTEGER DEFAULT 0,
                    last_active INTEGER DEFAULT (strftime('%s', 'now')),
                    is_banned INTEGER DEFAULT 0,
                    ban_reason TEXT,
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Таблица файлов
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    hash TEXT PRIMARY KEY,
                    remote_msg_id INTEGER,
                    type TEXT,
                    name TEXT,
                    game TEXT,
                    created_by INTEGER,
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Таблица приглашений
            conn.execute("""
                CREATE TABLE IF NOT EXISTS invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inviter_id INTEGER,
                    invited_id INTEGER UNIQUE,
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            # Таблица администраторов
            conn.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    added_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            
            conn.commit()
            
            # Добавляем владельца
            self._add_owner()
    
    def _add_owner(self):
        """Добавить владельца в админы"""
        from config import Config
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)",
                (Config.OWNER_ID, Config.OWNER_ID)
            )
            conn.commit()
    
    @contextmanager
    def transaction(self):
        """Контекстный менеджер для транзакций"""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Выполнить запрос"""
        with self.transaction() as conn:
            return conn.execute(query, params)
    
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Получить одну запись"""
        with self._get_conn() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchone()
    
    def fetch_all(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Получить все записи"""
        with self._get_conn() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
    
    # --- ПОЛЬЗОВАТЕЛИ ---
    def save_user(self, user_id: int, username: str = None, first_name: str = None, 
                  last_name: str = None, inviter_id: int = None):
        """Сохранить или обновить пользователя"""
        self.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, invited_by) 
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, first_name, last_name, inviter_id or 0))
        
        if inviter_id and inviter_id != user_id:
            self.execute("UPDATE users SET total_invites = total_invites + 1 WHERE user_id = ?", (inviter_id,))
            self.execute("INSERT OR IGNORE INTO invites (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user_id))
    
    def get_user(self, user_id: int):
        """Получить пользователя"""
        return self.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
    
    def get_all_users(self):
        """Получить всех пользователей"""
        return self.fetch_all("SELECT user_id FROM users WHERE is_banned = 0")
    
    def update_activity(self, user_id: int):
        """Обновить активность"""
        self.execute("UPDATE users SET last_active = strftime('%s', 'now') WHERE user_id = ?", (user_id,))
    
    # --- АДМИНЫ ---
    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь админом"""
        from config import Config
        if user_id == Config.OWNER_ID:
            return True
        admin = self.fetch_one("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
        return admin is not None
    
    def add_admin(self, user_id: int, added_by: int):
        """Добавить админа"""
        self.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (user_id, added_by))
    
    def remove_admin(self, user_id: int):
        """Удалить админа"""
        self.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    
    # --- ФАЙЛЫ ---
    def save_file(self, file_hash: str, remote_msg_id: int, file_type: str, 
                  name: str, game: str, created_by: int):
        """Сохранить файл"""
        self.execute("""
            INSERT INTO files (hash, remote_msg_id, type, name, game, created_by) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (file_hash, remote_msg_id, file_type, name, game, created_by))
    
    def get_file(self, file_hash: str):
        """Получить файл по хешу"""
        return self.fetch_one("SELECT * FROM files WHERE hash = ?", (file_hash,))
    
    def get_file_by_name(self, name: str):
        """Получить файл по названию"""
        return self.fetch_one("SELECT * FROM files WHERE name = ?", (name,))
    
    def get_all_games(self):
        """Получить все игры"""
        return self.fetch_all("SELECT DISTINCT game FROM files WHERE game IS NOT NULL AND game != ''")
    
    def get_files_by_game(self, game: str):
        """Получить файлы по игре"""
        return self.fetch_all("SELECT hash, name FROM files WHERE game = ?", (game,))
    
    def get_all_files(self):
        """Получить все файлы"""
        return self.fetch_all("SELECT name, game FROM files ORDER BY game, name")
    
    def delete_file(self, file_hash: str):
        """Удалить файл"""
        self.execute("DELETE FROM files WHERE hash = ?", (file_hash,))
    
    # --- СТАТИСТИКА ---
    def get_stats(self):
        """Получить статистику"""
        files = self.fetch_one("SELECT COUNT(*) FROM files")[0]
        users = self.fetch_one("SELECT COUNT(*) FROM users")[0]
        invites = self.fetch_one("SELECT SUM(total_invites) FROM users")[0] or 0
        return {
            'files': files,
            'users': users,
            'invites': invites
        }
    
    def cleanup_inactive(self, days: int = 30):
        """Очистка неактивных пользователей"""
        cursor = self.execute("""
            DELETE FROM users 
            WHERE strftime('%s', 'now') - last_active > ? * 86400
            AND user_id NOT IN (SELECT user_id FROM admins)
            AND user_id != ?
        """, (days, Config.OWNER_ID))
        return cursor.rowcount

# Создаем глобальный экземпляр
db = Database()
