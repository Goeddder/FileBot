import asyncio
import aiosqlite
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramRetryAfter

# --- НАСТРОЙКИ ---
API_TOKEN = '8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw'
BOT_USERNAME = "plutoniumfilesBot"
CHANNEL_ID = "@OfficialPlutonium"
ADMIN_ID = 1471307057

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Состояния для редактора фото приветствия
class EditWelcome(StatesGroup):
    waiting_for_photo = State()

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("files.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_id TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        # Текст приветствия по умолчанию
        default_text = "✋ Привет, {name}! Ты находишься в файловом боте @PlutoniumfilesBot\nКоторый хранит файлы канала @OfficialPlutonium"
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', ?)", (default_text,))
        await db.commit()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def get_setting(key):
    async with aiosqlite.connect("files.db") as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

def get_channel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Наш канал 📢", url="https://t.me/OfficialPlutonium")]
    ])

# --- ОБРАБОТЧИКИ ---

# 1. Меню редактора
@dp.message(Command("redacted"))
async def redactor_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Изменить фото приветствия", callback_data="edit_photo")]
    ])
    await message.answer("🛠 Меню редактора:", reply_markup=kb)

@dp.callback_query(F.data == "edit_photo")
async def start_edit_photo(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Пришли ФОТО, которое будет показываться при старте бота:")
    await state.set_state(EditWelcome.waiting_for_photo)

@dp.message(EditWelcome.waiting_for_photo, F.photo)
async def save_welcome_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('welcome_photo', ?)", (photo_id,))
        await db.commit()
    await state.clear()
    await message.answer("✅ Фото приветствия успешно обновлено!")

# 2. Рассылка (/send)
@dp.message(Command("send"))
async def start_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/send", "").strip()
    if not text:
        return await message.answer("Ошибка! Введите: /send Ваш текст")

    async with aiosqlite.connect("files.db") as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()

    count = 0
    for user in users:
        try:
            await bot.send_message(user[0], text)
            count += 1
            await asyncio.sleep(0.1) # Защита от Flood
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await bot.send_message(user[0], text)
            count += 1
        except Exception:
            continue
    await message.answer(f"✅ Рассылка завершена!\nПолучили: {count} чел.")

# 3. Обработка /start
@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    # Добавляем юзера в базу для рассылки
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    # Если перешли по ссылке на файл
    if command.args:
        if not await is_subscribed(message.from_user.id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться на канал 📢", url="https://t.me/OfficialPlutonium")],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data=f"check_{command.args}")]
            ])
            await message.answer("Для получения файла подпишись на наш канал!", reply_markup=kb)
            return

        # Если подписан - выдаем файл
        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id FROM files WHERE id = ?", (command.args,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await message.answer_document(document=row[0], caption="Ваш файл готов!", reply_markup=get_channel_kb())
                    return

    # Обычное приветствие
    welcome_template = await get_setting('welcome_text')
    user_name = message.from_user.first_name or "Друг"
    welcome_text = welcome_template.replace("{name}", user_name)
    photo = await get_setting('welcome_photo')

    if photo:
        await message.answer_photo(photo=photo, caption=welcome_text)
    else:
        await message.answer(welcome_text)

# 4. Проверка подписки по кнопке
@dp.callback_query(F.data.startswith("check_"))
async def check_subscription_btn(call: types.CallbackQuery):
    file_id_db = call.data.split("_")[1]
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id FROM files WHERE id = ?", (file_id_db,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await call.message.answer_document(document=row[0], caption="Лови файл!", reply_markup=get_channel_kb())
    else:
        await call.answer("❌ Ты еще не подписан на канал!", show_alert=True)

# 5. Загрузка файла админом
@dp.message(F.document | F.video | F.photo)
async def save_admin_file(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or await state.get_state() is not None: return
    
    # Получаем ID
    if message.document: f_id = message.document.file_id
    elif message.video: f_id = message.video.file_id
    else: f_id = message.photo[-1].file_id

    # Сохраняем
    async with aiosqlite.connect("files.db") as db:
        cursor = await db.execute("INSERT INTO files (file_id) VALUES (?)", (f_id,))
        await db.commit()
        last_id = cursor.lastrowid
    
    link = f"https://t.me/{BOT_USERNAME}?start={last_id}"
    await message.answer(f"✅ Файл добавлен!\nСсылка для поста: `{link}`", parse_mode="Markdown")
    
    # Дублируем файл с кнопкой для удобной пересылки
    if message.document:
        await message.answer_document(document=f_id, reply_markup=get_channel_kb())
    elif message.video:
        await message.answer_video(video=f_id, reply_markup=get_channel_kb())
    else:
        await message.answer_photo(photo=f_id, reply_markup=get_channel_kb())

# --- ЗАПУСК ---
async def main():
    await init_db()
    await bot.set_my_commands([BotCommand(command="start", description="Запуск бота")])
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот Plutonium Files запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    
