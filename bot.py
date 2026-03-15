import os
import datetime
import base64
import asyncio
from typing import Optional, Tuple

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    LabeledPrice, PreCheckoutQuery, CallbackQuery,
    Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F

import asyncpg

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = "8135974854:AAGg4Kbq39j1d7d7E5ViWVMr7O2jB_F9VIg"   # Твой токен
CHANNEL_USERNAME = "@BinarVPN"          # Канал для подписки
CHANNEL_ID = CHANNEL_USERNAME
PROVIDER_TOKEN = ""                      # Для Stars оставляем пустым

# URL базы данных PostgreSQL (будет задан переменной окружения)
DATABASE_URL = os.environ.get("DATABASE_URL")

# Пакеты пополнения
DEPOSIT_PACKS = {
    "stars_5": {"title": "5 ⭐", "price": 5, "stars": 5},
    "stars_10": {"title": "10 ⭐", "price": 10, "stars": 10},
    "stars_25": {"title": "25 ⭐", "price": 25, "stars": 25},
    "stars_50": {"title": "50 ⭐", "price": 50, "stars": 50},
    "stars_100": {"title": "100 ⭐", "price": 100, "stars": 100},
}

# ---------- ШАБЛОН ПОДПИСКИ (без строки expire) ----------
SUBSCRIPTION_TEMPLATE = """#profile-title: base64:dC5tZS9CaW5hclZQTg==
#profile-update-interval: 24
#support-url: https://t.me/BinarVPN
trojan://lEjtI3pFYfU7O1UYozJcfZV5K6Fwfths@64.74.163.118:58536?security=tls&insecure=1&allowInsecure=1&type=tcp&headerType=none#🇨🇦 Canada, Pointe-Claire | [BL]
trojan://pawxrlkLcJ@145.223.70.200:44056/?type=grpc&serviceName=&authority=&security=reality&pbk=asrnd4KrFBe5Ygz7LkvvsdMG-YnvChftudLamEVisk8&fp=chrome&sni=www.icloud.com&sid=8a&spx=/#🇨🇦 Canada, Toronto | 🌐 | [BL]
trojan://q2GRUM1-odJBWq_KV6xv2fuNvu8ed-@195.66.25.251:443?security=tls&sni=8443.golden-cards.me&type=tcp#🇱🇹 Lithuania, Vilnius | [BL]
trojan://q2GRUM1-odJBWq_KV6xv2fuNvu8ed-@8443.golden-cards.me:443?security=tls&sni=8443.golden-cards.me#🇱🇹 Lithuania, Vilnius | [BL]
trojan://q2GRUM1-odJBWq_KV6xv2fuNvu8ed-@8443.golden-cards.me:443?security=tls&sni=8443.golden-cards.me&fp=qq&insecure=0&allowInsecure=0&type=tcp&headerType=none#🇱🇹 Lithuania, Vilnius | [BL]
trojan://q2GRUM1-odJBWq_KV6xv2fuNvu8ed-@8443.golden-cards.me:443?type=raw&headerType=none&security=tls#🇱🇹 Lithuania, Vilnius | [BL]
trojan://wp9IsiY82uQhcmgNC1eoBM@80.173.231.254:12420?security=tls&sni=%F0%9F%94%92%20%5BBy%20EbraSha%5D%20&insecure=1&allowInsecure=1&type=tcp&headerType=none#🇳🇴 Norway, Oslo (Alna District) | [BL]
trojan://wp9IsiY82uQhcmgNC1eoBM@80.173.231.254:12420?security=tls&sni=%F0%9F%94%92%20By%20EbraSha%20&insecure=1&allowInsecure=1&type=tcp&headerType=none#🇳🇴 Norway, Oslo (Alna District) | [BL]
trojan://zp630tdUuD@194.150.166.151:52047/?type=grpc&serviceName=&authority=&security=reality&pbk=4o28aGSIz_r6Fa9sG7ZjgeT764t3bVJKmC9RDwIff38&fp=chrome&sni=aws.amazon.com&sid=1abe0c286879&spx=%2F#🇬🇧 United Kingdom, London | [BL]
trojan://kkzh2prsyr2ik47as615@64.94.95.118:57142?type=tcp&security=tls&sni=64.94.95.118&fp=random&allowInsecure=1#🇺🇸 United States, Dallas | [BL]"""

# ================== РАБОТА С БАЗОЙ ДАННЫХ (PostgreSQL) ==================

async def init_db():
    """Создаёт таблицу users, если её нет"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            subscription_until TIMESTAMP,
            trial_used BOOLEAN DEFAULT FALSE,
            registered TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    await conn.close()

async def get_user(user_id: int) -> dict:
    """Получает данные пользователя. Если нет — создаёт запись по умолчанию."""
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
    if row is None:
        # Создаём нового пользователя
        await conn.execute('''
            INSERT INTO users (user_id, balance, trial_used)
            VALUES ($1, 0, FALSE)
        ''', user_id)
        row = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
    await conn.close()
    return dict(row)

async def update_user(user_id: int, **kwargs):
    """Обновляет указанные поля пользователя"""
    if not kwargs:
        return
    sets = ', '.join(f"{key} = ${i+2}" for i, key in enumerate(kwargs.keys()))
    values = [user_id] + list(kwargs.values())
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(f'UPDATE users SET {sets} WHERE user_id = $1', *values)
    await conn.close()

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================

async def check_channel_subscription(user_id: int, bot: Bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return False

async def is_subscription_active(user_id: int) -> Tuple[bool, Optional[str]]:
    user = await get_user(user_id)
    until = user.get('subscription_until')
    if not until:
        return False, None
    # until уже может быть datetime объектом от asyncpg
    if isinstance(until, datetime.datetime):
        expire = until
    else:
        expire = datetime.datetime.fromisoformat(str(until))
    if expire > datetime.datetime.now():
        return True, expire.strftime('%d.%m.%Y %H:%M')
    return False, None

async def activate_trial(user_id: int) -> bool:
    user = await get_user(user_id)
    if user['trial_used']:
        return False
    expire = datetime.datetime.now() + datetime.timedelta(days=3)
    await update_user(user_id, subscription_until=expire, trial_used=True)
    return True

async def generate_subscription_file(user_id: int) -> Optional[str]:
    active, _ = await is_subscription_active(user_id)
    if not active:
        return None
    user = await get_user(user_id)
    expire_date = user['subscription_until']
    if isinstance(expire_date, str):
        expire_date = datetime.datetime.fromisoformat(expire_date)
    expire_timestamp = int(expire_date.timestamp())
    userinfo_line = f"#subscription-userinfo: upload=0; download=0; total=0; expire={expire_timestamp}"
    full_text = userinfo_line + "\n" + SUBSCRIPTION_TEMPLATE
    return base64.b64encode(full_text.encode()).decode()

# ================== ИНИЦИАЛИЗАЦИЯ БОТА ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== ОБРАБОТЧИКИ КОМАНД ==================

@dp.message(CommandStart())
async def start_command(message: Message):
    user_id = message.from_user.id
    await get_user(user_id)  # убедимся, что пользователь есть в базе
    welcome_text = (
        "👋 Добро пожаловать в BinarVPN!\n\n"
        "🔹 Нажми «Пробная подписка», чтобы получить 3 дня бесплатно (нужно подписаться на канал).\n"
        "🔹 В «Меню» ты найдёшь профиль, пополнение баланса и настройки."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Пробная подписка", callback_data="trial")],
        [InlineKeyboardButton(text="📋 Меню", callback_data="menu")]
    ])
    await message.answer(welcome_text, reply_markup=keyboard)

# ------------------ ПРОБНАЯ ПОДПИСКА ------------------
@dp.callback_query(F.data == "trial")
async def trial_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)

    if user['trial_used']:
        await callback.answer("Вы уже активировали пробную подписку!", show_alert=True)
        return

    subscribed = await check_channel_subscription(user_id, bot)
    if not subscribed:
        text = (
            f"Для получения пробной подписки на 3 дня подпишитесь на наш канал "
            f"{CHANNEL_USERNAME} и нажмите кнопку «Проверить»."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Перейти в канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_trial")]
        ])
        await callback.message.edit_text(text, reply_markup=keyboard)
    else:
        if await activate_trial(user_id):
            await callback.message.edit_text(
                "✅ Пробная подписка активирована! Действует 3 дня.\n"
                "Теперь вы можете получить конфиги в меню."
            )
        else:
            await callback.message.edit_text("❌ Ошибка активации.")
    await callback.answer()

@dp.callback_query(F.data == "check_trial")
async def check_trial_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    if user['trial_used']:
        await callback.answer("Пробная подписка уже активирована!", show_alert=True)
        return

    subscribed = await check_channel_subscription(user_id, bot)
    if subscribed:
        if await activate_trial(user_id):
            await callback.message.edit_text(
                "✅ Пробная подписка активирована! Действует 3 дня.\n"
                "Теперь вы можете получить конфиги в меню."
            )
        else:
            await callback.message.edit_text("❌ Ошибка активации.")
    else:
        await callback.answer("Вы ещё не подписались на канал!", show_alert=True)
    await callback.answer()

# ------------------ МЕНЮ ------------------
@dp.callback_query(F.data == "menu")
async def menu_callback(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="💰 Пополнить звёздами", callback_data="deposit")],
        [InlineKeyboardButton(text="🔌 Подключить устройство", callback_data="connect_device")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
    ])
    await callback.message.edit_text("📋 Главное меню", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    active, expire_str = await is_subscription_active(user_id)
    sub_status = f"✅ Активна до {expire_str}" if active else "❌ Не активна"
    text = (
        f"👤 **Ваш профиль**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"⭐ Баланс: {user['balance']} звёзд\n"
        f"📅 Подписка: {sub_status}\n"
        f"🎁 Пробная подписка: {'использована' if user['trial_used'] else 'доступна'}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu")]
    ])
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
    await callback.answer()

# ------------------ ПОПОЛНЕНИЕ ------------------
@dp.callback_query(F.data == "deposit")
async def deposit_callback(callback: CallbackQuery):
    text = "💰 Выберите сумму пополнения (1 ⭐ = 1 звезда Telegram):"
    builder = InlineKeyboardBuilder()
    for pack_id, pack in DEPOSIT_PACKS.items():
        builder.button(text=pack['title'], callback_data=f"buy_{pack_id}")
    builder.button(text="🔙 Назад", callback_data="menu")
    builder.adjust(2)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def buy_callback(callback: CallbackQuery):
    pack_id = callback.data.replace("buy_", "")
    pack = DEPOSIT_PACKS.get(pack_id)
    if not pack:
        await callback.answer("Ошибка: пакет не найден")
        return
    prices = [LabeledPrice(label=pack['title'], amount=pack['price'])]
    await callback.message.delete()
    await callback.message.answer_invoice(
        title="Пополнение баланса",
        description=f"Пополнение на {pack['stars']} звёзд",
        payload=pack_id,
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=prices,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Оплатить {pack['price']} звёзд", pay=True)]
        ])
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    pack = DEPOSIT_PACKS.get(payload)
    if pack:
        user = await get_user(user_id)
        new_balance = user['balance'] + pack['stars']
        await update_user(user_id, balance=new_balance)
        await message.answer(
            f"✅ Оплата прошла успешно!\n"
            f"На ваш баланс зачислено {pack['stars']} ⭐.\n"
            f"Текущий баланс: {new_balance} ⭐"
        )
    else:
        await message.answer("❌ Ошибка: пакет не найден")

# ------------------ ПОДКЛЮЧЕНИЕ УСТРОЙСТВА ------------------
@dp.callback_query(F.data == "connect_device")
async def connect_device_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    active, expire_str = await is_subscription_active(user_id)

    if not active:
        await callback.answer(
            "❌ У вас нет активной подписки. Активируйте пробную или пополните баланс.",
            show_alert=True
        )
        return

    WEB_SERVER_URL = os.environ.get("WEB_SERVER_URL", "https://binarvpn-web.onrender.com")
    sub_url = f"{WEB_SERVER_URL}/sub/{user_id}"

    guide_text = (
        f"🔌 **Подключение устройства**\n\n"
        f"Твоя подписка активна до {expire_str}.\n\n"
        f"**📱 Для V2RayTun:**\n"
        f"1. Открой приложение, нажми «+» → «Добавить подписку».\n"
        f"2. Вставь эту ссылку:\n`{sub_url}`\n\n"
        f"**📱 Для Happ:**\n"
        f"1. Перейди в раздел «Подписки» → «Добавить подписку».\n"
        f"2. Вставь ссылку.\n\n"
        f"После добавления клиент будет автоматически обновлять подписку (обычно раз в сутки)."
    )

    await callback.message.answer(guide_text, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()

# ------------------ НАЗАД ------------------
@dp.callback_query(F.data == "back_to_start")
async def back_to_start_callback(callback: CallbackQuery):
    await start_command(callback.message)
    await callback.answer()

# ================== ЗАПУСК ==================
async def main():
    # Инициализация базы данных перед запуском
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())