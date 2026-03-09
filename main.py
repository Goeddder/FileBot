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

# Логирование для отслеживания SIGTERM и ошибок
logging.basicConfig(level=logging.INFO)

API_TOKEN = '8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw'
BOT_USERNAME = "plutoniumfilesBot"
CHANNEL_ID = "@OfficialPlutonium"
ADMIN_ID = 1471307057

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class EditWelcome(StatesGroup):
    waiting_for_photo = State()

async def init_db():
    async with aiosqlite.connect("files.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_id TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        # Твой текст с поддержкой {name}
        default_text = "✋ Привет, {name}! Ты в боте @PlutoniumfilesBot\nХранилище файлов канала @OfficialPlutonium"
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', ?)", (default_text,))
        await db.commit()

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

# --- РАБОТА С КЛИЕНТАМИ ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message, command: CommandObject):
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    if command.args:
        if not await is_subscribed(message.from_user.id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться 📢", url="https://t.me/OfficialPlutonium")],
                [InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"check_{command.args}")]
            ])
            await message.answer("Подпишись, чтобы получить файл!", reply_markup=kb)
            return
        
        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id FROM files WHERE id = ?", (command.args,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await message.answer_document(document=row[0], caption="Твой файл готов!")
                    return

    welcome_template = await get_setting('welcome_text')
    # Безопасная замена имени
    name = message.from_user.first_name or "Пользователь"
    welcome_text = welcome_template.replace("{name}", name)
    photo = await get_setting('welcome_photo')

    if photo:
        await message.answer_photo(photo=photo, caption=welcome_text)
    else:
        await message.answer(welcome_text)

@dp.callback_query(F.data.startswith("check_"))
async def check_sub_and_give_file(call: types.CallbackQuery):
    file_id = call.data.split("_")[1]
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id FROM files WHERE id = ?", (file_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await call.message.answer_document(document=row[0])
    else:
        await call.answer("❌ Подписка не найдена!", show_alert=True)

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("redacted"))
async def redactor_menu(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Сменить фото приветствия", callback_data="edit_photo")]
        ])
        await message.answer("Редактор:", reply_markup=kb)

@dp.callback_query(F.data == "edit_photo")
async def start_edit_photo(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Пришли фото для приветствия:")
    await state.set_state(EditWelcome.waiting_for_photo)

@dp.message(EditWelcome.waiting_for_photo, F.photo)
async def save_new_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('welcome_photo', ?)", (photo_id,))
        await db.commit()
    await state.clear()
    await message.answer("✅ Фото сохранено!")

@dp.message(Command("send"))
async def start_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/send", "").strip()
    if not text: return await message.answer("Пример: /send Текст")

    async with aiosqlite.connect("files.db") as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
            
    count = 0
    for user in users:
        try:
            await bot.send_message(user[0], text)
            count += 1
            await asyncio.sleep(0.1) # Задержка от Flood
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await bot.send_message(user[0], text)
            count += 1
        except: continue
    await message.answer(f"✅ Рассылка: {count} чел.")

@dp.message(F.document | F.video | F.photo)
async def save_admin_file(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or await state.get_state(): return
    f_id = message.document.file_id if message.document else (message.video.file_id if message.video else message.photo[-1].file_id)
    async with aiosqlite.connect("files.db") as db:
        cursor = await db.execute("INSERT INTO files (file_id) VALUES (?)", (f_id,))
        await db.commit()
        last_id = cursor.lastrowid
    await message.answer(f"✅ Ссылка: `https://t.me/{BOT_USERNAME}?start={last_id}`")

# --- ЗАПУСК ---
async def main():
    await init_db()
    # Установка команд в меню
    await bot.set_my_commands([BotCommand(command="start", description="Запуск")])
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        print("Бот запущен. Ожидание обновлений...")
        await dp.start_polling(bot)
    finally:
        # Это сработает при SIGTERM (Railway)
        print("Закрытие соединений...")
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
        
