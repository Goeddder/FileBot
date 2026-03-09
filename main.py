import asyncio
import aiosqlite
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- НАСТРОЙКИ ---
API_TOKEN = '8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw'
BOT_USERNAME = "plutoniumfilesBot"
CHANNEL_ID = "@OfficialPlutonium"
ADMIN_ID = 1471307057

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Состояния для редактора
class EditWelcome(StatesGroup):
    waiting_for_photo = State()
    waiting_for_text = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("files.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_id TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        # Таблица для настроек приветствия
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        # Начальные значения, если пусто
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', 'Привет! Ты в боте OfficialPlutonium.')")
        await db.commit()

# --- ВСПОМОГАТЕЛЬНОЕ ---
async def get_setting(key):
    async with aiosqlite.connect("files.db") as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

def get_channel_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Наш канал 📢", url="https://t.me/OfficialPlutonium")]
    ])

# --- ОБРАБОТЧИКИ ---

# Команда /redacted
@dp.message(Command("redacted"))
async def redactor_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Изменить приветствие", callback_data="edit_welcome")]
    ])
    await message.answer("Меню редактора:", reply_markup=kb)

@dp.callback_query(F.data == "edit_welcome")
async def start_edit_welcome(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Пришли ФОТО для приветствия (или отправь /cancel для отмены):")
    await state.set_state(EditWelcome.waiting_for_photo)

@dp.message(EditWelcome.waiting_for_photo, F.photo)
async def process_welcome_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    await message.answer("Фото получено! Теперь напиши ТЕКСТ приветствия:")
    await state.set_state(EditWelcome.waiting_for_text)

@dp.message(EditWelcome.waiting_for_text)
async def process_welcome_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    photo_id = data['photo_id']
    welcome_text = message.text

    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('welcome_photo', ?)", (photo_id,))
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('welcome_text', ?)", (welcome_text,))
        await db.commit()

    await state.clear()
    await message.answer("✅ Приветствие успешно обновлено!")

# /start (Выдача файла или просто приветствие)
@dp.message(CommandStart())
async def start_cmd(message: types.Message, command: CommandObject):
    # Сохраняем юзера для рассылки
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    # Если это переход по ссылке на файл
    if command.args:
        if not await is_subscribed(message.from_user.id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться 📢", url="https://t.me/OfficialPlutonium")],
                [InlineKeyboardButton(text="Я подписался ✅", callback_data="check_sub")]
            ])
            await message.answer("Для получения файла подпишись на канал:", reply_markup=kb)
            return

        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id FROM files WHERE id = ?", (command.args,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await message.answer_document(document=row[0], caption="Лови файл!", reply_markup=get_channel_button())
                    return

    # Если просто /start
    text = await get_setting('welcome_text')
    photo = await get_setting('welcome_photo')

    if photo:
        await message.answer_photo(photo=photo, caption=text)
    else:
        await message.answer(text)

# Сохранение файлов админом (просто кидаешь файл - получаешь ссылку)
@dp.message(F.document | F.video | (F.photo & ~F.state(EditWelcome.waiting_for_photo)))
async def save_file_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    if message.document: f_id = message.document.file_id
    elif message.video: f_id = message.video.file_id
    else: f_id = message.photo[-1].file_id

    async with aiosqlite.connect("files.db") as db:
        cursor = await db.execute("INSERT INTO files (file_id) VALUES (?)", (f_id,))
        await db.commit()
        last_id = cursor.lastrowid
    
    await message.answer(f"✅ Файл добавлен!\nСсылка: `https://t.me/{BOT_USERNAME}?start={last_id}`")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
                
