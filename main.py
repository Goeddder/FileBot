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

class BotStates(StatesGroup):
    waiting_for_welcome_photo = State()
    waiting_for_file_number = State()

async def init_db():
    async with aiosqlite.connect("files.db") as db:
        # ДОБАВИЛИ колонку file_type для точной отправки
        await db.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_id TEXT, file_type TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        default_text = "✋ Привет, {name}! Ты в боте @PlutoniumfilesBot\nХранилище файлов @OfficialPlutonium"
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

# Универсальная функция отправки контента (чтобы не терялись из-за неверного метода)
async def send_any_file(chat_id, file_id, file_type, caption, reply_markup):
    try:
        if file_type == 'photo':
            await bot.send_photo(chat_id, photo=file_id, caption=caption, reply_markup=reply_markup)
        elif file_type == 'video':
            await bot.send_video(chat_id, video=file_id, caption=caption, reply_markup=reply_markup)
        else: # document и все остальное
            await bot.send_document(chat_id, document=file_id, caption=caption, reply_markup=reply_markup)
        return True
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

# --- ВЫДАЧА ФАЙЛА ---

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
            async with db.execute("SELECT file_id, file_type FROM files WHERE CAST(id AS TEXT) = ?", (file_arg,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    success = await send_any_file(message.chat.id, row[0], row[1], f"✅ Файл №{file_arg}", get_channel_kb())
                    if not success:
                        await message.answer("❌ Ошибка при попытке отправить файл. Возможно, он удален из серверов Telegram.")
                else:
                    await message.answer(f"❌ Файл {file_arg} не найден.")
        return

    welcome_template = await get_setting('welcome_text')
    name = message.from_user.first_name or "Друг"
    welcome_text = welcome_template.replace("{name}", name)
    photo = await get_setting('welcome_photo')
    if photo: await message.answer_photo(photo=photo, caption=welcome_text)
    else: await message.answer(welcome_text)

# --- CALLBACK ---

@dp.callback_query(F.data.startswith("chk_"))
async def check_btn(call: types.CallbackQuery):
    f_num = str(call.data.split("_")[1])
    
    if await is_subscribed(call.from_user.id):
        async with aiosqlite.connect("files.db") as db:
            async with db.execute("SELECT file_id, file_type FROM files WHERE CAST(id AS TEXT) = ?", (f_num,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await call.message.delete()
                    await send_any_file(call.message.chat.id, row[0], row[1], f"✅ Файл №{f_num}", get_channel_kb())
                else:
                    await call.answer("❌ Ошибка: файл исчез из базы!", show_alert=True)
    else:
        await call.answer("❌ Ты всё еще не подписан!", show_alert=True)

# --- АДМИНКА ---

@dp.message(F.document | F.video | F.photo)
async def admin_upload(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or await state.get_state(): return
    
    # Определяем тип и ID корректно
    if message.document:
        f_id, f_type = message.document.file_id, 'document'
    elif message.video:
        f_id, f_type = message.video.file_id, 'video'
    elif message.photo:
        f_id, f_type = message.photo[-1].file_id, 'photo'
    
    await state.update_data(temp_f_id=f_id, temp_type=f_type)
    await message.answer(f"📥 {f_type.capitalize()} принят! Введи **НОМЕР**:")
    await state.set_state(BotStates.waiting_for_file_number)

@dp.message(BotStates.waiting_for_file_number)
async def save_with_number(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введи только число!")
        return
    num = int(message.text)
    data = await state.get_data()
    async with aiosqlite.connect("files.db") as db:
        # Сохраняем и ID и ТИП
        await db.execute("INSERT OR REPLACE INTO files (id, file_id, file_type) VALUES (?, ?, ?)", 
                         (num, data['temp_f_id'], data['temp_type']))
        await db.commit()
    await message.answer(f"✅ Сохранено под №{num}!\nСсылка: `https://t.me/{BOT_USERNAME}?start={num}`")
    await state.clear()

# --- Остальные функции без изменений ---
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
    
