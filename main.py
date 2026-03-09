import asyncio
import aiosqlite
import os
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

# Состояния для редактора и загрузки файлов
class BotStates(StatesGroup):
    waiting_for_welcome_photo = State()
    waiting_for_file_number = State()

# --- ИНИЦИАЛИЗАЦИЯ БД ---
async def init_db():
    async with aiosqlite.connect("files.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_id TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        # Текст приветствия по умолчанию
        default_text = "✋ Привет, {name}! Ты находишься в файловом боте @PlutoniumfilesBot\nКоторый хранит файлы канала @OfficialPlutonium"
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

def get_channel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Наш канал 📢", url="https://t.me/OfficialPlutonium")]
    ])

# --- ОБРАБОТЧИК /START (Выдача и приветствие) ---

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject):
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    if command.args:
        if not await is_subscribed(message.from_user.id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться 📢", url="https://t.me/OfficialPlutonium")],
                [InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"check_{command.args}")]
            ])
            await message.answer("⚠️ Подпишись на канал, чтобы скачать файл!", reply_markup=kb)
            return

        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id FROM files WHERE id = ?", (command.args,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await message.answer_document(document=row[0], caption="✅ Файл найден!", reply_markup=get_channel_kb())
                else:
                    await message.answer("❌ Файл с таким номером не найден.")
        return

    welcome_template = await get_setting('welcome_text')
    name = message.from_user.first_name or "Друг"
    welcome_text = welcome_template.replace("{name}", name)
    photo = await get_setting('welcome_photo')

    if photo:
        await message.answer_photo(photo=photo, caption=welcome_text)
    else:
        await message.answer(welcome_text)

# --- НОВАЯ ЛОГИКА ЗАГРУЗКИ ФАЙЛА АДМИНОМ ---

@dp.message(F.document | F.video | F.photo)
async def admin_file_upload_step1(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or await state.get_state(): return
    
    # Определяем file_id
    f_id = message.document.file_id if message.document else (message.video.file_id if message.video else message.photo[-1].file_id)
    
    # Сохраняем временно file_id в состояние
    await state.update_data(temp_file_id=f_id, temp_msg_type=message.content_type)
    
    await message.answer("📁 Файл получен! Теперь напиши **НОМЕР**, под которым его сохранить:")
    await state.set_state(BotStates.waiting_for_file_number)

@dp.message(BotStates.waiting_for_file_number)
async def admin_file_upload_step2(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Ошибка! Введи только цифры (номер файла):")
        return

    file_number = int(message.text)
    data = await state.get_data()
    f_id = data['temp_file_id']

    async with aiosqlite.connect("files.db") as db:
        # Проверяем, не занят ли номер
        async with db.execute("SELECT id FROM files WHERE id = ?", (file_number,)) as cursor:
            if await cursor.fetchone():
                await message.answer(f"⚠️ Номер {file_number} уже занят! Введи другой или удали старый.")
                return
        
        await db.execute("INSERT INTO files (id, file_id) VALUES (?, ?)", (file_number, f_id))
        await db.commit()

    link = f"https://t.me/{BOT_USERNAME}?start={file_number}"
    await message.answer(f"✅ Файл успешно сохранен под номером **{file_number}**!\n\nСсылка для поста:\n`{link}`", parse_mode="Markdown")
    
    # Выдаем файл с кнопкой для пересылки
    if data['temp_msg_type'] == 'document':
        await message.answer_document(document=f_id, reply_markup=get_channel_kb())
    elif data['temp_msg_type'] == 'video':
        await message.answer_video(video=f_id, reply_markup=get_channel_kb())
    else:
        await message.answer_photo(photo=f_id, reply_markup=get_channel_kb())

    await state.clear()

# --- ОСТАЛЬНОЕ (Редактор приветствия, кнопки, рассылка) ---

@dp.callback_query(F.data.startswith("check_"))
async def check_sub_btn(call: types.CallbackQuery):
    f_num = call.data.split("_")[1]
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id FROM files WHERE id = ?", (f_num,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await call.message.answer_document(document=row[0], reply_markup=get_channel_kb())
    else:
        await call.answer("❌ Подписка не найдена!", show_alert=True)

@dp.message(Command("redacted"))
async def redacted_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🖼 Изменить фото приветствия", callback_data="edit_photo")]])
        await message.answer("Меню настроек:", reply_markup=kb)

@dp.callback_query(F.data == "edit_photo")
async def edit_photo_call(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("Пришли новое фото для старта:")
    await state.set_state(BotStates.waiting_for_welcome_photo)

@dp.message(BotStates.waiting_for_welcome_photo, F.photo)
async def save_welcome_photo(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('welcome_photo', ?)", (photo_id,))
        await db.commit()
    await state.clear()
    await message.answer("✅ Фото приветствия обновлено!")

@dp.message(Command("send"))
async def broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/send", "").strip()
    if not text: return await message.answer("Напиши: /send Текст")
    async with aiosqlite.connect("files.db") as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], text)
            count += 1
            await asyncio.sleep(0.1)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await bot.send_message(u[0], text)
            count += 1
        except: continue
    await message.answer(f"✅ Рассылка: {count} чел.")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
