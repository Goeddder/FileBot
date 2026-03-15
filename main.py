import os
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== НАСТРОЙКИ ==========
API_ID = 39522849
API_HASH = "26909eddad0be2400fb765fad0e267f8"
BOT_TOKEN = "8071432823:AAFZImIckEGin220ZJR9WL4abbEUy_p5OZw"
ADMIN_ID = 1471307057
# ================================

app = Client("simple_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Простая команда /start
@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"✅ Бот работает!\n"
        f"🆔 Твой ID: `{message.from_user.id}`"
    )

# Команда /admin (только для админа)
@app.on_message(filters.command("admin") & filters.user(ADMIN_ID))
async def admin_command(client, message):
    await message.reply("👑 Ты админ, команда работает!")

# Команда /help для всех
@app.on_message(filters.command("help"))
async def help_command(client, message):
    await message.reply(
        "📋 Доступные команды:\n"
        "/start - приветствие\n"
        "/help - это меню\n"
        "/admin - для админа"
    )

# Обработка любого текста (для теста)
@app.on_message(filters.text & filters.private)
async def echo(client, message):
    await message.reply(f"Ты написал: {message.text}")

print("🚀 Бот запускается...")
app.run()
