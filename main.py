import asyncio
import aiosqlite
import os
import logging
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

class BotStates(StatesGroup):
    waiting_for_welcome_photo = State()
    waiting_for_file_number = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("files.db") as db:
        # Убеждаемся, что ID — это INTEGER PRIMARY KEY
        await db.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_id TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
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

def get_channel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Наш канал 📢", url="https://t.me/OfficialPlutonium")]
    ])

# --- ЛОГИКА /START ---

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject, state: FSMContext):
    # Сброс любого состояния админа при нажатии старт
    await state.clear()
    
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    # ЕСЛИ ПЕРЕШЛИ ЗА ФАЙЛОМ
    if command.args:
        file_arg = command.args
        print(f"DEBUG: Поиск файла с ID: {file_arg}") # Увидишь в консоли Pydroid

        if not await is_subscribed(message.from_user.id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться 📢", url="https://t.me/OfficialPlutonium")],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data=f"check_{file_arg}")]
            ])
            await message.answer("⚠️ Для доступа к файлу нужно быть в канале!", reply_markup=kb)
            return

        async with aiosqlite.connect("files.db") as db:
            # Ищем файл, преобразуя аргумент в число
            async with db.execute("SELECT file_id FROM files WHERE id = ?", (file_arg,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await message.answer_document(document=row[0], caption=f"✅ Файл #{file_arg} готов!", reply_markup=get_channel_kb())
                else:
                    await message.answer(f"❌ Файл с номером {file_arg} не найден в базе.")
        return

    # ОБЫЧНЫЙ СТАРТ
    welcome_template = await get_setting('welcome_text')
    name = message.from_user.first_name or "Друг"
    welcome_text = welcome_template.replace("{name}", name)
    photo = await get_setting('welcome_photo')

    if photo:
        await message.answer_photo(photo=photo, caption=welcome_text)
    else:
        await message.answer(welcome_text)

# --- РУЧНОЕ ДОБАВЛЕНИЕ НОМЕРА (ТВОЙ ЗАПРОС) ---

@dp.message(F.document | F.video | F.photo)
async def admin_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or await state.get_state(): return
    
    f_id = message.document.file_id if message.document else (message.video.file_id if message.video else message.photo[-1].file_id)
    await state.update_data(temp_f_id=f_id, temp_type=message.content_type)
    
    await message.answer("📥 Файл принят! Введи **НОМЕР** для этого файла:")
    await state.set_state(BotStates.waiting_for_file_number)

@dp.message(BotStates.waiting_for_file_number)
async def save_with_number(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введи только ЧИСЛО!")
        return

    num = int(message.text)
    data = await state.get_data()
    f_id = data['temp_f_id']

    async with aiosqlite.connect("files.db") as db:
        # Проверяем на дубликат
        async with db.execute("SELECT id FROM files WHERE id = ?", (num,)) as cursor:
            if await cursor.fetchone():
                await message.answer(f"⚠️ Номер {num} уже используется. Введи другой:")
                return
        
        await db.execute("INSERT INTO files (id, file_id) VALUES (?, ?)", (num, f_id))
        await db.commit()

    await message.answer(f"✅ Сохранено под №{num}!\nСсылка: `https://t.me/{BOT_USERNAME}?start={num}`", parse_mode="Markdown")
    await state.clear()

# --- ПРОВЕРКА ПО КНОПКЕ ---
@dp.callback_query(F.data.startswith("check_"))
async def check_btn(call: types.CallbackQuery):
    f_num = call.data.split("_")[1]
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id FROM files WHERE id = ?", (f_num,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await call.message.answer_document(document=row[0], reply_markup=get_channel_kb())
    else:
        await call.answer("❌ Ты не подписан!", show_alert=True)

# --- ОСТАЛЬНОЕ ---
@dp.message(Command("redacted"))
async def red_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🖼 Сменить фото", callback_data="edit_photo")]])
        await message.answer("Редактор приветствия:", reply_markup=kb)

@dp.callback_query(F.data == "edit_photo")
async def edit_p(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Кидай фото:")
    await state.set_state(BotStates.waiting_for_welcome_photo)

@dp.message(BotStates.waiting_for_welcome_photo, F.photo)
async def save_p(message: types.Message, state: FSMContext):
    p_id = message.photo[-1].file_id
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('welcome_photo', ?)", (p_id,))
        await db.commit()
    await state.clear()
    await message.answer("✅ Готово!")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
        
