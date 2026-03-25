from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from config import Config

class Keyboards:
    """Все клавиатуры бота"""
    
    @staticmethod
    def main() -> ReplyKeyboardMarkup:
        """Главная клавиатура для всех пользователей"""
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("🎮 Игры")],
                [KeyboardButton("👤 Профиль"), KeyboardButton("🔗 Рефералка")],
                [KeyboardButton("❓ Помощь")]
            ],
            resize_keyboard=True
        )
    
    @staticmethod
    def admin() -> ReplyKeyboardMarkup:
        """Админ-панель"""
        return ReplyKeyboardMarkup(
            [
                [KeyboardButton("📁 Добавить чит"), KeyboardButton("📋 Список читов")],
                [KeyboardButton("👥 Пользователи"), KeyboardButton("📢 Рассылка")],
                [KeyboardButton("📊 Статистика"), KeyboardButton("🧹 Очистка")],
                [KeyboardButton("💾 Бэкап"), KeyboardButton("🔙 Главное меню")]
            ],
            resize_keyboard=True
        )
    
    @staticmethod
    def games(games_list: list) -> ReplyKeyboardMarkup:
        """Клавиатура с играми"""
        if not games_list:
            return Keyboards.main()
        
        buttons = []
        for g in games_list[:20]:
            game = g['game'] if isinstance(g, dict) else g[0]
            buttons.append([KeyboardButton(f"🎮 {game}")])
        
        buttons.append([KeyboardButton("🔙 Главное меню")])
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    
    @staticmethod
    def cheats(cheats_list: list) -> ReplyKeyboardMarkup:
        """Клавиатура с читами"""
        if not cheats_list:
            return Keyboards.back_to_games()
        
        buttons = []
        for c in cheats_list[:20]:
            name = c['name'] if isinstance(c, dict) else c[1]
            buttons.append([KeyboardButton(f"📄 {name[:30]}")])
        
        buttons.append([KeyboardButton("🔙 Назад к играм")])
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    
    @staticmethod
    def subscribe() -> InlineKeyboardMarkup:
        """Кнопка подписки"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 ПОДПИСАТЬСЯ НА КАНАЛ", url=Config.CHANNEL_URL)],
            [InlineKeyboardButton("🔄 ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub")]
        ])
    
    @staticmethod
    def back_to_games() -> ReplyKeyboardMarkup:
        """Кнопка возврата к играм"""
        return ReplyKeyboardMarkup(
            [[KeyboardButton("🔙 Назад к играм")]],
            resize_keyboard=True
        )
