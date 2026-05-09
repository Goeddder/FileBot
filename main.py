import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8743517612:AAFrgMXZpRnDQclyuiRYNKSziV-TPhkB_S8"
ADMIN_ID = 7496589494
CRYPTO_BOT_TOKEN = "560372:AAyQpvWZFSHpzrnVAhVwPF7PbcJmqI7bH0K"  # Твой токен CryptoPay
UAH_CARD = "4441111008011946"
UAH_COMMENT = "За цифрові товари"

# Цены (USDT и UAH)
PRICES = {
    "Lebro [Lite]": {"24h": 1.5, "7d": 4.5},
    "Lebro [VIP]": {"24h": 3, "7d": 7.5, "30d": 15},
    "Plutonium": {"7d": 150, "30d": 300, "90d": 700},
}

# Периоды для отображения
PERIODS = {
    "Lebro [Lite]": [("24 часа", "24h"), ("7 дней", "7d")],
    "Lebro [VIP]": [("24 часа", "24h"), ("7 дней", "7d"), ("30 дней", "30d")],
    "Plutonium": [("7 дней", "7d"), ("30 дней", "30d"), ("90 дней", "90d")],
}

# ========== ХРАНЕНИЕ ДАННЫХ ==========
DATA_FILE = "bot_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}, "pending_uah": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

data = load_data()

# ========== FSM СОСТОЯНИЯ ==========
class AgreementState(StatesGroup):
    waiting_agreement = State()

class PaymentState(StatesGroup):
    waiting_game = State()
    waiting_product = State()
    waiting_period = State()
    waiting_payment_method = State()
    waiting_uah_receipt = State()

class AdminState(StatesGroup):
    waiting_user_id_for_keys = State()
    waiting_key_input = State()
    waiting_pending_approval = State()

# ========== КЛАВИАТУРЫ ==========
def get_agreement_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ознакомлен", callback_data="agree")]
    ])

def get_main_keyboard(is_admin=False):
    buttons = [
        [KeyboardButton(text="🛍 Каталог")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Мои покупки")]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="🔑 Админ: Выдать ключ")])
        buttons.append([KeyboardButton(text="💰 Админ: Подтвердить UAH")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_catalog_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔥 Oxide Survival Island", callback_data="game_oxide")
    builder.button(text="💥 Standoff 2", callback_data="game_standoff")
    builder.adjust(1)
    return builder.as_markup()

def get_products_keyboard(game):
    builder = InlineKeyboardBuilder()
    if game == "oxide":
        builder.button(text="Lebro [VIP]", callback_data="product_Lebro [VIP]")
        builder.button(text="Lebro [Lite]", callback_data="product_Lebro [Lite]")
    else:
        builder.button(text="Plutonium", callback_data="product_Plutonium")
    builder.button(text="🔙 Назад", callback_data="back_to_catalog")
    builder.adjust(1)
    return builder.as_markup()

def get_periods_keyboard(product):
    builder = InlineKeyboardBuilder()
    for period_name, period_key in PERIODS[product]:
        builder.button(text=period_name, callback_data=f"period_{period_key}")
    builder.button(text="🔙 Назад", callback_data="back_to_products")
    builder.adjust(1)
    return builder.as_markup()

def get_payment_methods_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="💸 CryptoPay (USDT)", callback_data="pay_crypto")
    builder.button(text="🇺🇦 Оплата гривной (карта)", callback_data="pay_uah")
    builder.button(text="🔙 Назад", callback_data="back_to_periods")
    builder.adjust(1)
    return builder.as_markup()

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ==========
def register_user(user_id, username, full_name):
    if str(user_id) not in data["users"]:
        data["users"][str(user_id)] = {
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "active_key": None,
            "expires_at": None,
            "purchases": [],
            "agreed": False
        }
        save_data(data)

def add_purchase(user_id, product, period, price, currency, key=None, status="pending"):
    purchase = {
        "product": product,
        "period": period,
        "price": price,
        "currency": currency,
        "purchased_at": datetime.now().isoformat(),
        "status": status,
        "key": key
    }
    data["users"][str(user_id)]["purchases"].append(purchase)
    if status == "active" and key:
        data["users"][str(user_id)]["active_key"] = key
        expires = datetime.now() + timedelta(days=int(period.replace("d", ""))) if period.endswith("d") else datetime.now() + timedelta(hours=24)
        data["users"][str(user_id)]["expires_at"] = expires.isoformat()
    save_data(data)

# ========== ХЭНДЛЕРЫ ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Старт + проверка согласия
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user = message.from_user
    register_user(user.id, user.username, user.full_name)
    
    if not data["users"][str(user.id)].get("agreed", False):
        rules_text = """📜 *Правила PlayCheatGameBot* 

🚫 1. Возврат:
Возврата нет — при покупке цифрового товара потеря, неправильное использование никто не компенсирует.

⚠️ 2. Ответственность:
Исполнитель не несёт ответственности за последствия применения.

📜 3. Общие:
Оплачивая услугу, вы соглашаетесь с данными правилами.

🛡 4. Заключительные:
Исполнитель вправе изменять условия.

✅ Нажми *Ознакомлен* чтобы продолжить"""
        await message.answer(rules_text, parse_mode="Markdown", reply_markup=get_agreement_keyboard())
        await state.set_state(AgreementState.waiting_agreement)
    else:
        await show_menu(message)

@dp.callback_query(F.data == "agree", StateFilter(AgreementState.waiting_agreement))
async def agree_rules(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data["users"][str(user_id)]["agreed"] = True
    save_data(data)
    await callback.message.delete()
    await callback.message.answer("✅ Добро пожаловать! Теперь ты можешь пользоваться ботом.", reply_markup=get_main_keyboard(user_id == ADMIN_ID))
    await show_menu(callback.message)
    await state.clear()

async def show_menu(message: types.Message):
    text = """🛡 *PlayCheatGameBot* - Надёжный магазин читов для игр!

✅ *Почему мы?*
• Моментальная автоматическая выдача
• 24/7 поддержка
• Проверенные софты без Root
• Анонимная оплата криптой

*Выбери действие:*"""
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard(message.from_user.id == ADMIN_ID))

# Каталог
@dp.message(F.text == "🛍 Каталог")
async def catalog(message: types.Message):
    text = "📋 *Выбери игру:*"
    await message.answer(text, parse_mode="Markdown", reply_markup=get_catalog_keyboard())

@dp.callback_query(F.data.startswith("game_"))
async def select_game(callback: types.CallbackQuery, state: FSMContext):
    game = callback.data.split("_")[1]
    await state.update_data(game=game)
    text = "🎮 *Выбери продукт:*"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_products_keyboard(game))

@dp.callback_query(F.data.startswith("product_"))
async def select_product(callback: types.CallbackQuery, state: FSMContext):
    product = callback.data.replace("product_", "")
    await state.update_data(product=product)
    text = f"📦 *{product}*\nВыбери период:"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_periods_keyboard(product))

@dp.callback_query(F.data.startswith("period_"))
async def select_period(callback: types.CallbackQuery, state: FSMContext):
    period = callback.data.replace("period_", "")
    await state.update_data(period=period)
    data_state = await state.get_data()
    product = data_state["product"]
    
    price = PRICES[product][period]
    currency = "USDT" if "Lebro" in product else "UAH"
    
    text = f"""💸 *К оплате:* {price} {currency}

Подтверди способ оплаты:"""
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_payment_methods_keyboard())

@dp.callback_query(F.data == "pay_crypto")
async def pay_crypto(callback: types.CallbackQuery, state: FSMContext):
    data_state = await state.get_data()
    product = data_state["product"]
    period = data_state["period"]
    price = PRICES[product][period]
    
    # Здесь интеграция с CryptoPay API
    # В демо-версии просто имитация
    invoice_link = f"https://t.me/send?start={CRYPTO_BOT_TOKEN}_{int(price*100)}"
    text = f"""💳 *Оплата через CryptoPay*

Сумма: {price} USDT
Товар: {product} ({period})

👉 [Оплатить]({invoice_link})

После оплаты чек придет автоматически, и ключ будет выдан."""
    await callback.message.edit_text(text, parse_mode="Markdown", disable_web_page_preview=True)
    # Имитация успешной оплаты (в реальности нужен webhook от CryptoPay)
    # Для демо выдаем ключ от админа
    await callback.message.answer("⚠️ В демо-режиме оплата не проходит. Напиши админу для теста.")
    # Реальная интеграция требует вебхук

@dp.callback_query(F.data == "pay_uah")
async def pay_uah(callback: types.CallbackQuery, state: FSMContext):
    data_state = await state.get_data()
    product = data_state["product"]
    period = data_state["period"]
    price = PRICES[product][period]
    
    text = f"""🇺🇦 *Оплата гривной*

Сумма: {price} грн
Товар: {product} ({period})

💳 Карта: `{UAH_CARD}`
❗ Обязательно комментарий: `{UAH_COMMENT}`

После оплаты отправь скриншот чека сюда ⬇️"""
    await callback.message.edit_text(text, parse_mode="Markdown")
    await state.set_state(PaymentState.waiting_uah_receipt)
    await state.update_data(price=price, product=product, period=period)

@dp.message(PaymentState.waiting_uah_receipt, F.photo)
async def receive_receipt(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data_state = await state.get_data()
    photo_id = message.photo[-1].file_id
    
    pending_id = f"{user_id}_{datetime.now().timestamp()}"
    data["pending_uah"][pending_id] = {
        "user_id": user_id,
        "product": data_state["product"],
        "period": data_state["period"],
        "price": data_state["price"],
        "photo": photo_id,
        "username": message.from_user.username
    }
    save_data(data)
    
    # Уведомление админу
    admin_text = f"""🔔 *Новая оплата UAH*

👤 Пользователь: @{message.from_user.username} (ID: {user_id})
📦 Товар: {data_state['product']} ({data_state['period']})
💰 Сумма: {data_state['price']} грн

Чек прикреплен ниже.
Используй кнопку *Админ: Подтвердить UAH* для выдачи ключа."""
    await bot.send_photo(ADMIN_ID, photo_id, caption=admin_text, parse_mode="Markdown")
    
    await message.answer("✅ Чек отправлен администратору. Ожидайте выдачи ключа.")
    await state.clear()

# Профиль
@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    user = data["users"][str(message.from_user.id)]
    active = user.get("active_key")
    expires = user.get("expires_at")
    
    text = f"""👤 *Ваш профиль*

🆔 ID: {user['user_id']}
📛 Юзернейм: @{user['username']}
🔑 Активный ключ: {active if active else 'Нет'}
⏳ Срок до: {expires if expires else '—'}"""
    await message.answer(text, parse_mode="Markdown")

# Мои покупки
@dp.message(F.text == "📦 Мои покупки")
async def my_purchases(message: types.Message):
    purchases = data["users"][str(message.from_user.id)].get("purchases", [])
    if not purchases:
        await message.answer("📭 У вас пока нет покупок.")
        return
    
    text = "📜 *История покупок:*\n\n"
    for p in purchases:
        text += f"🔹 {p['product']} ({p['period']}) - {p['price']} {p['currency']}\n   Статус: {p['status']}\n   Ключ: {p.get('key', '—')}\n\n"
    await message.answer(text, parse_mode="Markdown")

# Админ: выдать ключ
@dp.message(F.text == "🔑 Админ: Выдать ключ")
async def admin_give_key(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("✏️ Введи ID пользователя, которому выдать ключ:")
    await state.set_state(AdminState.waiting_user_id_for_keys)

@dp.message(AdminState.waiting_user_id_for_keys)
async def get_user_id_for_key(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        if str(user_id) not in data["users"]:
            await message.answer("❌ Пользователь не найден.")
            await state.clear()
            return
        await state.update_data(target_user=user_id)
        await message.answer("🔑 Введи ключ (или текст, который выдать пользователю):")
        await state.set_state(AdminState.waiting_key_input)
    except:
        await message.answer("❌ Введи корректный ID (число).")

@dp.message(AdminState.waiting_key_input)
async def give_key(message: types.Message, state: FSMContext):
    key = message.text
    data_state = await state.get_data()
    user_id = data_state["target_user"]
    
    # Активируем ключ пользователю
    data["users"][str(user_id)]["active_key"] = key
    data["users"][str(user_id)]["expires_at"] = (datetime.now() + timedelta(days=30)).isoformat()
    # Добавляем в покупки
    add_purchase(user_id, "Выдано админом", "30d", 0, "ADMIN", key=key, status="active")
    save_data(data)
    
    await bot.send_message(user_id, f"✅ Администратор выдал вам ключ:\n`{key}`\n\nСпасибо за покупку!", parse_mode="Markdown")
    await message.answer(f"✅ Ключ выдан пользователю {user_id}")
    await state.clear()

# Админ: подтвердить UAH
@dp.message(F.text == "💰 Админ: Подтвердить UAH")
async def admin_confirm_uah(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if not data["pending_uah"]:
        await message.answer("📭 Нет ожидающих подтверждений.")
        return
    
    text = "📋 *Выбери оплату для подтверждения:*\n"
    buttons = []
    for pid, info in data["pending_uah"].items():
        text += f"\n🔹 ID: {pid}\n   От: @{info['username']}\n   Товар: {info['product']} ({info['period']})\n"
        buttons.append([InlineKeyboardButton(text=f"Выдать @{info['username']}", callback_data=f"approve_{pid}")])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("approve_"))
async def approve_uah(callback: types.CallbackQuery, state: FSMContext):
    pending_id = callback.data.replace("approve_", "")
    pending = data["pending_uah"].get(pending_id)
    if not pending:
        await callback.answer("Уже обработано!", show_alert=True)
        return
    
    user_id = pending["user_id"]
    product = pending["product"]
    period = pending["period"]
    
    # Выдаем ключ (здесь ты можешь ввести ключ вручную)
    await callback.message.answer(f"✏️ Введи ключ для пользователя @{pending['username']} (товар {product}):")
    await state.update_data(target_user=user_id, product=product, period=period, pending_id=pending_id)
    await state.set_state(AdminState.waiting_pending_approval)

@dp.message(AdminState.waiting_pending_approval)
async def finish_uah_approval(message: types.Message, state: FSMContext):
    key = message.text
    data_state = await state.get_data()
    user_id = data_state["target_user"]
    product = data_state["product"]
    period = data_state["period"]
    pending_id = data_state["pending_id"]
    
    # Добавляем покупку
    price = PRICES[product][period]
    add_purchase(user_id, product, period, price, "UAH", key=key, status="active")
    
    # Удаляем из pending
    del data["pending_uah"][pending_id]
    save_data(data)
    
    await bot.send_message(user_id, f"✅ Ваша оплата подтверждена!\n🔑 Ваш ключ: `{key}`\n📦 Товар: {product} ({period})", parse_mode="Markdown")
    await message.answer(f"✅ Ключ выдан пользователю {user_id}")
    await state.clear()

# Навигация назад
@dp.callback_query(F.data == "back_to_catalog")
async def back_to_catalog(callback: types.CallbackQuery):
    await callback.message.edit_text("📋 *Выбери игру:*", parse_mode="Markdown", reply_markup=get_catalog_keyboard())

@dp.callback_query(F.data == "back_to_products")
async def back_to_products(callback: types.CallbackQuery, state: FSMContext):
    data_state = await state.get_data()
    game = data_state.get("game", "oxide")
    await callback.message.edit_text("🎮 *Выбери продукт:*", parse_mode="Markdown", reply_markup=get_products_keyboard(game))

@dp.callback_query(F.data == "back_to_periods")
async def back_to_periods(callback: types.CallbackQuery, state: FSMContext):
    data_state = await state.get_data()
    product = data_state["product"]
    await callback.message.edit_text(f"📦 *{product}*\nВыбери период:", parse_mode="Markdown", reply_markup=get_periods_keyboard(product))

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
