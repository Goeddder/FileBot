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
DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class BotStates(StatesGroup):
    waiting_for_welcome_photo = State()
    waiting_for_file_number = State()

async def init_db():
    async with aiosqlite.connect("files.db") as db:
        # id теперь TEXT, чтобы можно было использовать любые метки (числа или буквы)
        await db.execute("CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, file_id TEXT, file_type TEXT, file_path TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
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

# 
async def send_safe_file(chat_id, file_info, caption):
    f_id, f_type, f_path = file_info
    markup = get_channel_kb()
    
    # План А: Быстрая отправка через Telegram ID
    try:
        if f_type == 'photo': await bot.send_photo(chat_id, photo=f_id, caption=caption, reply_markup=markup)
        elif f_type == 'video': await bot.send_video(chat_id, video=f_id, caption=caption, reply_markup=markup)
        else: await bot.send_document(chat_id, document=f_id, caption=caption, reply_markup=markup)
        return True
    except Exception as e:
        print(f"ID-отправка не удалась ({e}), использую локальный файл...")

    # План Б: Гарантированная отправка с диска
    if f_path and os.path.exists(f_path):
        try:
            input_file = FSInputFile(f_path)
            if f_type == 'photo': await bot.send_photo(chat_id, photo=input_file, caption=caption, reply_markup=markup)
            elif f_type == 'video': await bot.send_video(chat_id, video=input_file, caption=caption, reply_markup=markup)
            else: await bot.send_document(chat_id, document=input_file, caption=caption, reply_markup=markup)
            return True
        except Exception as e2:
            print(f"Ошибка при отправке с диска: {e2}")
    
    await bot.send_message(chat_id, "⚠️ Файл временно недоступен. Попробуйте еще раз.")
    return False

# --- ОБРАБОТЧИКИ ---

@dp.message(CommandStart())
async def start_handler(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    
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
            async with db.execute("SELECT file_id, file_type, file_path FROM files WHERE id = ?", (file_arg,)) as cursor:
                row = await cursor.fetchone()
                if row: await send_safe_file(message.chat.id, row, f"✅ Файл №{file_arg}")
                else: await message.answer("❌ Файл не найден.")
        return

    # Главное приветствие
    await message.answer("✋ Привет! Используй /start <номер> для получения файла.")

@dp.callback_query(F.data.startswith("chk_"))
async def check_btn(call: types.CallbackQuery):
    f_num = call.data.split("_")[1]
    if await is_subscribed(call.from_user.id):
        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id, file_type, file_path FROM files WHERE id = ?", (f_num,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await call.message.delete()
                    await send_safe_file(call.message.chat.id, row, f"✅ Файл №{f_num}")
                else: await call.answer("❌ Файл не найден!")
    else: await call.answer("❌ Вы не подписаны!", show_alert=True)

@dp.message(F.document | F.video | F.photo)
async def admin_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    if message.document: f_id, f_type, f_name = message.document.file_id, 'doc', message.document.file_name
    elif message.video: f_id, f_type, f_name = message.video.file_id, 'video', f"v_{message.video.file_unique_id}.mp4"
    else: f_id, f_type, f_name = message.photo[-1].file_id, 'photo', f"p_{message.photo[-1].file_unique_id}.jpg"

    file_info = await bot.get_file(f_id)
    local_path = os.path.join(DOWNLOAD_DIR, f_name)
    await bot.download_file(file_info.file_path, local_path)
    
    await state.update_data(temp_f_id=f_id, temp_type=f_type, temp_path=local_path)
    await message.answer("📥 Файл принят! Введи **номер или название**:")
    await state.set_state(BotStates.waiting_for_file_number)

@dp.message(BotStates.waiting_for_file_number)
async def save_with_number(message: types.Message, state: FSMContext):
    f_key = message.text.strip()
    data = await state.get_data()
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?)", 
                         (f_key, data['temp_f_id'], data['temp_type'], data['temp_path']))
        await db.commit()
    await message.answer(f"✅ Сохранено под: {f_key}\nСсылка: `https://t.me/{BOT_USERNAME}?start={f_key}`")
    await state.clear()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
