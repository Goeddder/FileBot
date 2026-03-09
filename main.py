import asyncio
import aiosqlite
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- НАСТРОЙКИ ---
API_TOKEN = '8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw'
BOT_USERNAME = "plutoniumfilesBot"
CHANNEL_ID = "@OfficialPlutonium"
ADMIN_ID = 1471307057
DOWNLOAD_DIR = "downloads" # Папка для локальных копий

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class BotStates(StatesGroup):
    waiting_for_welcome_photo = State()
    waiting_for_file_number = State()

async def init_db():
    async with aiosqlite.connect("files.db") as db:
        # file_path — путь к копии на диске
        await db.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_id TEXT, file_type TEXT, file_path TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        default_text = "✋ Привет, {name}! Ты в боте @PlutoniumfilesBot\nХранилище файлов @OfficialPlutonium"
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', ?)", (default_text,))
        await db.commit()

async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

def get_channel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Наш канал 📢", url="https://t.me/OfficialPlutonium")]
    ])

# --- УМНАЯ ОТПРАВКА (С ПРОВЕРКОЙ ЛОКАЛЬНОЙ КОПИИ) ---
async def send_safe_file(chat_id, file_info, caption):
    f_id, f_type, f_path = file_info
    markup = get_channel_kb()
    
    try:
        # 1. Пробуем отправить по ID (быстрый способ)
        if f_type == 'photo': await bot.send_photo(chat_id, photo=f_id, caption=caption, reply_markup=markup)
        elif f_type == 'video': await bot.send_video(chat_id, video=f_id, caption=caption, reply_markup=markup)
        else: await bot.send_document(chat_id, document=f_id, caption=caption, reply_markup=markup)
    except Exception:
        # 2. Если ID протух, пробуем отправить файл с диска
        if f_path and os.path.exists(f_path):
            input_file = FSInputFile(f_path)
            if f_type == 'photo': await bot.send_photo(chat_id, photo=input_file, caption=caption, reply_markup=markup)
            elif f_type == 'video': await bot.send_video(chat_id, video=input_file, caption=caption, reply_markup=markup)
            else: await bot.send_document(chat_id, document=input_file, caption=caption, reply_markup=markup)
        else:
            await bot.send_message(chat_id, "❌ К сожалению, файл полностью утерян.")

# --- ЛОГИКА БОТА ---

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    if command.args:
        file_arg = str(command.args)
        if not await is_subscribed(message.from_user.id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Подписаться 📢", url="https://t.me/OfficialPlutonium")],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data=f"chk_{file_arg}")]
            ])
            await message.answer("⚠️ Подпишись на канал, чтобы получить файл!", reply_markup=kb)
            return

        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id, file_type, file_path FROM files WHERE CAST(id AS TEXT) = ?", (file_arg,)) as cursor:
                row = await cursor.fetchone()
                if row: await send_safe_file(message.chat.id, row, f"✅ Файл №{file_arg}")
                else: await message.answer(f"❌ Файл {file_arg} не найден.")
        return

    # Приветствие (стандартное)
    async with aiosqlite.connect("files.db") as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'welcome_text'") as c:
            row = await c.fetchone()
            welcome_text = row[0].replace("{name}", message.from_user.first_name or "Друг")
        async with db.execute("SELECT value FROM settings WHERE key = 'welcome_photo'") as c:
            photo = await c.fetchone()
            if photo: await message.answer_photo(photo=photo[0], caption=welcome_text)
            else: await message.answer(welcome_text)

@dp.callback_query(F.data.startswith("chk_"))
async def check_btn(call: types.CallbackQuery):
    f_num = str(call.data.split("_")[1])
    if await is_subscribed(call.from_user.id):
        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id, file_type, file_path FROM files WHERE CAST(id AS TEXT) = ?", (f_num,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await call.message.delete()
                    await send_safe_file(call.message.chat.id, row, f"✅ Файл №{f_num}")
                else: await call.answer("❌ Файл не найден!", show_alert=True)
    else: await call.answer("❌ Ты всё еще не подписан!", show_alert=True)

# --- АДМИНКА (ЗАГРУЗКА И СОХРАНЕНИЕ) ---

@dp.message(F.document | F.video | F.photo)
async def admin_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or await state.get_state(): return
    
    if message.document: f_id, f_type, f_name = message.document.file_id, 'doc', message.document.file_name
    elif message.video: f_id, f_type, f_name = message.video.file_id, 'video', f"video_{message.video.file_unique_id}.mp4"
    else: f_id, f_type, f_name = message.photo[-1].file_id, 'photo', f"img_{message.photo[-1].file_unique_id}.jpg"

    msg = await message.answer("⏳ Скачиваю файл для резервной копии...")
    
    # Скачиваем файл на диск
    file = await bot.get_file(f_id)
    local_path = os.path.join(DOWNLOAD_DIR, f_name)
    await bot.download_file(file.file_path, local_path)
    
    await state.update_data(temp_f_id=f_id, temp_type=f_type, temp_path=local_path)
    await msg.edit_text(f"📥 {f_type} сохранен локально! Введи **НОМЕР**:")
    await state.set_state(BotStates.waiting_for_file_number)

@dp.message(BotStates.waiting_for_file_number)
async def save_with_number(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введи число!")
        return
    num = int(message.text)
    data = await state.get_data()
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR REPLACE INTO files (id, file_id, file_type, file_path) VALUES (?, ?, ?, ?)", 
                         (num, data['temp_f_id'], data['temp_type'], data['temp_path']))
        await db.commit()
    await message.answer(f"✅ Готово! №{num}\nСсылка: `https://t.me/{BOT_USERNAME}?start={num}`")
    await state.clear()

# --- ОСТАЛЬНОЕ ---
@dp.message(Command("redacted"))
async def red_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🖼 Сменить фото", callback_data="edit_photo")]])
        await message.answer("Редактор:", reply_markup=kb)

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
    await message.answer("✅ Фото обновлено!")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
                                      
