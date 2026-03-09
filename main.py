import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand

API_TOKEN = '8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw'
BOT_USERNAME = "plutoniumfilesBot"
CHANNEL_ID = "@OfficialPlutonium"
ADMIN_ID = 1471307057

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect("files.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS files (id INTEGER PRIMARY KEY, file_id TEXT)")
        # Таблица для рассылки (собираем всех юзеров)
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.commit()

# --- КНОПКИ ---
def get_channel_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Наш канал 📢", url="https://t.me/OfficialPlutonium")]
    ])

# --- ЛОГИКА ---

# Проверка подписки
async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

# 1. Выдача файла с кнопкой
@dp.message(CommandStart(deep_link=True))
async def handle_deep_link(message: types.Message, command: CommandObject):
    # Сохраняем юзера в базу для рассылки
    async with aiosqlite.connect("files.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    if not await is_subscribed(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться 📢", url="https://t.me/OfficialPlutonium")],
            [InlineKeyboardButton(text="Я подписался ✅", callback_data="check_sub")]
        ])
        await message.answer("Для получения файла подпишись:", reply_markup=kb)
        return

    file_key = command.args
    async with aiosqlite.connect("files.db") as db:
        async with db.execute("SELECT file_id FROM files WHERE id = ?", (file_key,)) as cursor:
            row = await cursor.fetchone()
            if row:
                # ВОТ ЗДЕСЬ КНОПКА ДОБАВЛЕНА:
                await message.answer_document(document=row[0], caption="Лови файл!", reply_markup=get_channel_button())
            else:
                await message.answer("Ошибка: файл не найден.")

# 2. Команда рассылки /send
@dp.message(Command("send"))
async def start_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    # Текст рассылки берется из аргументов команды, например: /send Привет всем!
    text = message.text.replace("/send ", "")
    if text == "/send":
        await message.answer("Используй: /send Текст рассылки")
        return

    async with aiosqlite.connect("files.db") as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
            count = 0
            for user in users:
                try:
                    await bot.send_message(user[0], text)
                    count += 1
                except:
                    continue
            await message.answer(f"✅ Рассылка завершена! Получателей: {count}")

# Остальные команды...
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(f"Добро пожаловать {message.from_user.first_name}Ты в боте PlutoniumFilesBot!")

@dp.message(F.document | F.photo | F.video)
async def save_file(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    if message.document: f_id = message.document.file_id
    elif message.video: f_id = message.video.file_id
    else: f_id = message.photo[-1].file_id

    async with aiosqlite.connect("files.db") as db:
        cursor = await db.execute("INSERT INTO files (file_id) VALUES (?)", (f_id,))
        await db.commit()
        last_id = cursor.lastrowid
    await message.answer(f"✅ Ссылка: `https://t.me/{BOT_USERNAME}?start={last_id}`", parse_mode="Markdown")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
                                              
