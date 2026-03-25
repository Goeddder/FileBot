from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

class Keyboards:
    """Все клавиатуры бота"""
    
    @staticmethod
    def main() -> ReplyKeyboardMarkup:
        """Главная клавиатура"""
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
        buttons = [[KeyboardButton(f"🎮 {g['game']}")] for g in games_list[:20]]
        buttons.append([KeyboardButton("🔙 Главное меню")])
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    
    @staticmethod
    def cheats(cheats_list: list) -> ReplyKeyboardMarkup:
        """Клавиатура с читами"""
        buttons = [[KeyboardButton(f"📄 {c['name'][:30]}")] for c in cheats_list[:20]]
        buttons.append([KeyboardButton("🔙 Назад к играм")])
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    
    @staticmethod
    def subscribe() -> InlineKeyboardMarkup:
        """Кнопка подписки"""
        from config import Config
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url=Config.CHANNEL_URL)],
            [InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data="check_sub")]
        ])
    
    @staticmethod
    def back_to_games() -> ReplyKeyboardMarkup:
        """Кнопка возврата к играм"""
        return ReplyKeyboardMarkup(
            [[KeyboardButton("🔙 Назад к играм")]],
            resize_keyboard=True
        )
