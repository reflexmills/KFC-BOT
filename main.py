import os
import json
import asyncio
import requests
import asyncio
import logging
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# Настройки платежей
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")
CRYPTO_BOT_API_URL = "https://pay.crypt.bot/api"
USDT_RATE = Decimal('79')  # Курс USDT к рублю
YOOMONEY_WALLET = "-"  # Номер кошелька
SUPPORT_USERNAME = "@KFC_SERVIS"  # юз поддержки

# База данных
DB_FILE = 'database.json'
temp_orders = {}  # Временное хранилище неоплаченных заказов
temp_deposits = {}  # Временные данные о пополнениях

# Классы состояний
class OrderStates(StatesGroup):
    choosing_platform = State()
    choosing_service = State()
    entering_quantity = State()
    choosing_duration = State()
    choosing_date = State()
    choosing_time = State()
    entering_channel = State()
    confirmation = State()

class PaymentStates(StatesGroup):
    choosing_amount = State()
    confirmation = State()

class AdminStates(StatesGroup):
    managing_orders = State()
    adding_admin = State()
    removing_admin = State()
    changing_balance = State()

# Цены услуг (теперь цена за 1 единицу)
SERVICE_PRICES = {
    "Подписчики": {"price": 1, "min": 10, "unit": "шт", "type": "quantity"},
    "Живой чат RU": {"price": 319, "min": 1, "unit": "час", "type": "duration"},
    "Живой чат ENG": {"price": 419, "min": 1, "unit": "час", "type": "duration"},
    "Зрители": {"price": 1, "min": 10, "unit": "шт", "type": "quantity"}
}

# Словарь изображений платформ
PLATFORM_IMAGES = {
    "YouTube": "https://radikal.cloud/i/photo-5350495139111499792-y.VJefY6",
    "Twitch": "https://radikal.cloud/i/photo-5350495139111499793-m.VJe8sx",
    "Kick": "https://radikal.cloud/i/photo-5350495139111499794-m.VJe9Qg"
}

# Вспомогательные функции
def load_db():
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'users': {}, 'orders': {}, 'admins': [6402443549], 'settings': {}}

def save_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

def get_main_kb(user_id):
    db = load_db()
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="🛍️ Заказать услугу"))
    kb.add(KeyboardButton(text="👤 Профиль"))
    kb.add(KeyboardButton(text="🆘 Поддержка"))
    if user_id in db['admins']:
        kb.add(KeyboardButton(text="👑 Админ"))
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def get_back_kb():
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="🔙 Назад"))
    return kb.as_markup(resize_keyboard=True)

async def convert_rub_to_usdt(rub_amount):
    return (Decimal(rub_amount) / USDT_RATE).quantize(Decimal('0.00'), rounding=ROUND_DOWN)

# Хендлеры команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db = load_db()
    user_id = message.from_user.id
    
    if str(user_id) not in db['users']:
        db['users'][str(user_id)] = {
            'balance': 0,
            'orders': [],
            'registration_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'username': message.from_user.username
        }
        save_db(db)
    
    await message.answer_photo(
        photo="https://imgfoto.host/i/cQwJbA",
        caption="👋 <b>Добро пожаловать в бота для продвижения стримов!</b>\n\n"
                "Здесь вы можете:\n"
                "• 🛍️ Заказать услуги продвижения\n"
                "• 💰 Пополнить баланс\n"
                "• 📊 Отслеживать статистику",
        reply_markup=get_main_kb(user_id),
        parse_mode="HTML"
    )

@dp.message(F.text == "🔙 Назад")
async def cmd_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=get_main_kb(message.from_user.id))

# Система заказов
@dp.message(F.text == "🛍️ Заказать услугу")
async def cmd_order(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="🎮 Kick"))
    kb.add(KeyboardButton(text="📺 YouTube"))
    kb.add(KeyboardButton(text="🟣 Twitch"))
    kb.add(KeyboardButton(text="🔙 Назад"))
    kb.adjust(2)
    
    await message.answer_photo(
        photo="https://imgfoto.host/i/cQEhtk",
        caption="Выберите платформу:",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(OrderStates.choosing_platform)
    
@dp.message(OrderStates.choosing_platform, F.text.in_(["🎮 Kick", "📺 YouTube", "🟣 Twitch"]))
async def process_platform(message: types.Message, state: FSMContext):
    platform_map = {
        "🎮 Kick": "Kick",
        "📺 YouTube": "YouTube",
        "🟣 Twitch": "Twitch"
    }
    selected_platform = platform_map[message.text]
    await state.update_data(platform=selected_platform)
    
    platform_image = PLATFORM_IMAGES.get(selected_platform)
    
    kb = ReplyKeyboardBuilder()
    for service in SERVICE_PRICES:
        kb.add(KeyboardButton(text=service))
    kb.add(KeyboardButton(text="🔙 Назад"))
    kb.adjust(2)
    
    if platform_image:
        await message.answer_photo(
            photo=platform_image,
            caption=f"<b>Выбрана платформа: {selected_platform}</b>\n\nВыберите услугу:",
            reply_markup=kb.as_markup(resize_keyboard=True),
            parse_mode="HTML"
        )
    await state.set_state(OrderStates.choosing_service)

@dp.message(OrderStates.choosing_service, F.text.in_(list(SERVICE_PRICES.keys())))
async def process_service(message: types.Message, state: FSMContext):
    service = message.text
    price_info = SERVICE_PRICES[service]
    await state.update_data(service=service, price_info=price_info)
    
    if price_info['type'] == "quantity":
        await message.answer(
            f"Услуга: {service}\n"
            f"Цена: {price_info['price']} руб/{price_info['unit']}\n"
            f"Минимальный заказ: {price_info['min']} {price_info['unit']}\n\n"
            "Введите количество:",
            reply_markup=get_back_kb()
        )
        await state.set_state(OrderStates.entering_quantity)
    elif price_info['type'] == "duration":
        kb = ReplyKeyboardBuilder()
        for hours in [1, 2, 3, 4, 5, 6]:
            kb.add(KeyboardButton(text=f"{hours} час(а)"))
        kb.add(KeyboardButton(text="🔙 Назад"))
        kb.adjust(3)
        
        await message.answer(
            f"Услуга: {service}\n"
            f"Цена: {price_info['price']} руб/{price_info['unit']}\n"
            f"Минимальный заказ: {price_info['min']} {price_info['unit']}\n\n"
            "Выберите длительность стрима:",
            reply_markup=kb.as_markup(resize_keyboard=True)
        )
        await state.set_state(OrderStates.choosing_duration)

@dp.message(OrderStates.entering_quantity, F.text.regexp(r'^\d+$'))
async def process_quantity(message: types.Message, state: FSMContext):
    quantity = int(message.text)
    data = await state.get_data()
    price_info = data['price_info']
    
    if quantity < price_info['min']:
        await message.answer(f"Минимальное количество: {price_info['min']}. Введите другое значение:")
        return
    
    total_price = quantity * price_info['price']
    await state.update_data(quantity=quantity, total_price=total_price)
    
    await message.answer(
        "Введите дату стрима в формате ДД.ММ (например, 15.06):",
        reply_markup=get_back_kb()
    )
    await state.set_state(OrderStates.choosing_date)

@dp.message(OrderStates.choosing_duration, F.text.regexp(r'^\d+\sчас\(а\)$'))
async def process_duration(message: types.Message, state: FSMContext):
    duration = int(message.text.split()[0])
    data = await state.get_data()
    price_info = data['price_info']
    
    if duration < price_info['min']:
        await message.answer(f"Минимальная длительность: {price_info['min']} час. Введите другое значение:")
        return
    
    total_price = duration * price_info['price']
    await state.update_data(duration=duration, total_price=total_price)
    
    await message.answer(
        "Введите дату стрима в формате ДД.ММ (например, 15.06):",
        reply_markup=get_back_kb()
    )
    await state.set_state(OrderStates.choosing_date)

@dp.message(OrderStates.choosing_date, F.text.regexp(r'^\d{2}\.\d{2}$'))
async def process_date(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text)
    await message.answer(
        "Введите время начала стрима в формате ЧЧ:ММ (например, 14:00):",
        reply_markup=get_back_kb()
    )
    await state.set_state(OrderStates.choosing_time)

@dp.message(OrderStates.choosing_time, F.text.regexp(r'^\d{2}:\d{2}$'))
async def process_time(message: types.Message, state: FSMContext):
    await state.update_data(time=message.text)
    await message.answer(
        "Введите название вашего канала (например, 'MyCoolChannel'):",
        reply_markup=get_back_kb()
    )
    await state.set_state(OrderStates.entering_channel)

@dp.message(OrderStates.entering_channel)
async def process_channel(message: types.Message, state: FSMContext):
    await state.update_data(channel=message.text)
    data = await state.get_data()
    price_info = data['price_info']
    
    if price_info['type'] == "quantity":
        details = f"Количество: {data['quantity']} {price_info['unit']}"
    else:
        details = f"Длительность: {data['duration']} {price_info['unit']}"
    
    confirmation_msg = (
        "📝 <b>Подтвердите заказ:</b>\n\n"
        f"1. Платформа: {data['platform']}\n"
        f"2. Услуга: {data['service']}\n"
        f"3. {details}\n"
        f"4. Канал: {data['channel']}\n"
        f"5. Дата стрима: {data['date']}\n"
        f"6. Время начала: {data['time']}\n\n"
        f"💰 <b>Сумма к оплате: {data['total_price']} руб</b>"
    )
    
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="✅ Подтвердить"))
    kb.add(KeyboardButton(text="❌ Отменить"))
    kb.add(KeyboardButton(text="🔙 Назад"))
    kb.adjust(2)
    
    await message.answer(confirmation_msg, reply_markup=kb.as_markup(resize_keyboard=True), parse_mode="HTML")
    await state.set_state(OrderStates.confirmation)

@dp.message(OrderStates.confirmation, F.text == "✅ Подтвердить")
async def confirm_order(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    order_data = {
        'platform': data['platform'],
        'service': data['service'],
        'channel': data['channel'],
        'date': data['date'],
        'time': data['time'],
        'amount': data['total_price'],
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    if data['price_info']['type'] == "quantity":
        order_data['quantity'] = data['quantity']
    else:
        order_data['duration'] = data['duration']
    
    temp_orders[user_id] = order_data
    
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="💰 Оплатить CryptoBot"))
    kb.add(KeyboardButton(text="💳 Оплатить картой"))
    kb.add(KeyboardButton(text="🔙 Назад"))
    kb.adjust(2)
    
    await message.answer(
        "🛒 <b>Ваш заказ ожидает оплаты</b>\n"
        f"Сумма к оплате: {data['total_price']} руб\n\n"
        "Выберите способ оплаты:",
        reply_markup=kb.as_markup(resize_keyboard=True),
        parse_mode="HTML"
    )
    
    await state.clear()

# Система оплаты
@dp.message(F.text == "💳 Оплатить картой")
async def card_payment_handler(message: types.Message):
    payment_text = f"""
✨ <b>Оплата банковской картой</b> ✨

Для завершения оплаты:

1. Напишите нашему менеджеру: {SUPPORT_USERNAME}
2. Укажите ID ващего Telegram
3. Оплатите счет

Мы принимаем:
• 💳 Visa/Mastercard/МИР
• 🏦 Перевод с любого банка РФ
• 📱 ЮMoney/СБП

⏳ Обычно обработка занимает <b>5-15 минут</b> (10:00-20:00 МСК)
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Написать в поддержку", url=f"https://t.me/{SUPPORT_USERNAME[1:]}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="payment_back")]
    ])
    await message.answer(payment_text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "payment_back")
async def payment_back(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer()

@dp.message(F.text == "💰 Оплатить CryptoBot")
async def cryptobot_payment_handler(message: types.Message):
    user_id = message.from_user.id
    if user_id not in temp_orders:
        await message.answer("❌ Нет заказов для оплаты", reply_markup=get_back_kb())
        return

    order_data = temp_orders[user_id]
    rub_amount = Decimal(str(order_data['amount']))
    usdt_amount = await convert_rub_to_usdt(rub_amount)

    # Проверка минимальной суммы
    if usdt_amount < Decimal('1.00'):
        await message.answer(
            f"❌ Минимальная сумма 1 USDT (~{USDT_RATE} руб)\n"
            f"Ваша сумма: {usdt_amount} USDT",
            reply_markup=get_back_kb()
        )
        return

    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "asset": "USDT",
        "amount": str(usdt_amount),
        "description": f"Оплата заказа",
        "payload": f"order_{user_id}",
        "allow_anonymous": False
    }

    try:
        response = requests.post(f"{CRYPTO_BOT_API_URL}/createInvoice", headers=headers, json=payload)
        response.raise_for_status()
        invoice = response.json()['result']
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить сейчас", url=invoice['pay_url'])],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_{invoice['invoice_id']}")]
        ])
        
        await message.answer(
            f"💎 <b>Оплата через CryptoBot</b>\n\n"
            f"▪ Сумма: <b>{rub_amount} руб</b>\n"
            f"▪ В USDT: <b>{usdt_amount}</b>\n"
            f"▪ Курс: 1 USDT = {USDT_RATE} руб\n\n"
            "⏳ Счет действителен <b>15 минут</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        
        asyncio.create_task(check_cryptobot_payment(invoice['invoice_id'], user_id, rub_amount, usdt_amount))
        
    except Exception as e:
        logger.error(f"CryptoBot error: {e}")
        await message.answer(
            "⚠ Произошла ошибка при создании счета. Попробуйте позже.",
            reply_markup=get_back_kb()
        )

async def check_cryptobot_payment(invoice_id, user_id, rub_amount, usdt_amount):
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    
    for _ in range(30):  # Проверяем в течение 15 минут
        await asyncio.sleep(30)
        try:
            response = requests.get(f"{CRYPTO_BOT_API_URL}/getInvoices?invoice_ids={invoice_id}", headers=headers)
            response.raise_for_status()
            invoice = response.json()['result']['items'][0]
            
            if invoice['status'] == 'paid':
                db = load_db()
                user_id_str = str(user_id)
                
                # Создаем заказ в БД
                order_id = len(db['orders']) + 1
                db['orders'][str(order_id)] = {
                    'user_id': user_id,
                    **temp_orders[user_id],
                    'status': 'paid',
                    'paid_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'invoice_id': invoice_id
                }
                
                # Добавляем в профиль пользователя
                if user_id_str not in db['users']:
                    db['users'][user_id_str] = {
                        'balance': 0,
                        'orders': [],
                        'username': (await bot.get_chat(user_id)).username
                    }
                
                db['users'][user_id_str]['orders'].append(order_id)
                save_db(db)
                
                # Удаляем из временного хранилища
                del temp_orders[user_id]
                
                # Уведомляем пользователя
                await bot.send_message(
                    user_id,
                    f"✅ <b>Заказ #{order_id} успешно оплачен!</b>\n\n"
                    f"▫️ Сумма: {rub_amount} руб\n"
                    f"▫️ В USDT: {usdt_amount}\n"
                    f"▫️ Курс: 1 USDT = {USDT_RATE} руб\n\n"
                    "🛠 Заказ взят в работу!",
                    reply_markup=get_main_kb(user_id),
                    parse_mode="HTML"
                )
                
                # Уведомляем админов
                for admin_id in db['admins']:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"🆕 <b>Новый оплаченный заказ #{order_id}</b>\n\n"
                            f"👤 Пользователь: @{db['users'][user_id_str].get('username', 'N/A')}\n"
                            f"💰 Сумма: {rub_amount} руб (~{usdt_amount} USDT)\n"
                            f"🛒 Услуга: {temp_orders[user_id]['service']}",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.error(f"Admin notification error: {e}")
                
                return
                
        except Exception as e:
            logger.error(f"Payment check error: {e}")
    
    # Если оплата не прошла
    if user_id in temp_orders:
        await bot.send_message(
            user_id,
            "⌛ Время на оплату истекло. Заказ автоматически отменен.",
            reply_markup=get_main_kb(user_id)
        )
        del temp_orders[user_id]

@dp.callback_query(F.data.startswith("check_"))
async def check_payment_handler(callback: types.CallbackQuery):
    invoice_id = callback.data.split("_")[1]
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    
    try:
        response = requests.get(f"{CRYPTO_BOT_API_URL}/getInvoices?invoice_ids={invoice_id}", headers=headers)
        response.raise_for_status()
        invoice = response.json()['result']['items'][0]
        
        if invoice['status'] == 'paid':
            await callback.answer("✅ Оплата уже зачислена!", show_alert=True)
        else:
            await callback.answer("ℹ️ Оплата еще не поступила", show_alert=True)
    except Exception as e:
        logger.error(f"Payment check error: {e}")
        await callback.answer("⚠ Ошибка проверки, попробуйте позже", show_alert=True)

# Профиль и баланс
@dp.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    db = load_db()
    user_id = str(message.from_user.id)
    user_data = db['users'].get(user_id, {})
    
    if not user_data:
        await message.answer("Профиль не найден. Начните с команды /start")
        return
    
    orders_count = len(user_data.get('orders', []))
    paid_orders = sum(1 for oid in user_data.get('orders', []) 
                  if db['orders'].get(str(oid), {}).get('status') == 'paid')
    
    profile_text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"▫️ ID: {user_id}\n"
        f"▫️ Дата регистрации: {user_data.get('registration_date')}\n"
        f"💰 Баланс: {user_data.get('balance', 0)} руб\n\n"
        f"📊 <b>Статистика заказов</b>\n"
        f"▫️ Всего: {orders_count}\n"
        f"▫️ Оплачено: {paid_orders}"
    )
    
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="🛍️ Мои заказы"))
    kb.add(KeyboardButton(text="💳 Пополнить баланс"))
    kb.add(KeyboardButton(text="🔙 Назад"))
    kb.adjust(2)
    
    await message.answer(profile_text, reply_markup=kb.as_markup(resize_keyboard=True), parse_mode="HTML")

@dp.message(F.text == "🛍️ Мои заказы")
async def show_user_orders(message: types.Message):
    db = load_db()
    user_id = str(message.from_user.id)
    user_data = db['users'].get(user_id, {})
    
    if not user_data or not user_data.get('orders'):
        await message.answer("У вас нет оплаченных заказов.")
        return
    
    orders_text = "📋 <b>Ваши заказы</b>\n\n"
    for order_id in user_data['orders']:
        order = db['orders'].get(str(order_id))
        if order and order['status'] == 'paid':
            orders_text += (
                f"🆔 <b>#{order_id}</b>\n"
                f"▫️ Услуга: {order['service']}\n"
                f"▫️ Платформа: {order['platform']}\n"
                f"▫️ Канал: {order['channel']}\n"
                f"▫️ Дата: {order['date']} {order['time']}\n"
                f"▫️ Сумма: {order['amount']} руб\n"
                f"▫️ Статус: {order['status']}\n"
                f"————————————\n"
            )
    
    await message.answer(orders_text, parse_mode="HTML")

@dp.message(F.text == "💳 Пополнить баланс")
async def cmd_deposit(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите сумму пополнения в рублях (минимум 100 руб):",
        reply_markup=get_back_kb()
    )
    await state.set_state(PaymentStates.choosing_amount)

@dp.message(PaymentStates.choosing_amount, F.text.regexp(r'^\d+$'))
async def process_deposit_amount(message: types.Message, state: FSMContext):
    amount = int(message.text)
    if amount < 100:
        await message.answer("Минимальная сумма пополнения - 100 руб. Введите другую сумму:")
        return
    
    await state.update_data(amount=amount)
    
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="💰 Оплатить CryptoBot"))
    kb.add(KeyboardButton(text="💳 Оплатить картой"))
    kb.add(KeyboardButton(text="🔙 Назад"))
    kb.adjust(2)
    
    await message.answer(
        f"Сумма пополнения: {amount} руб\n\nВыберите способ оплаты:",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(PaymentStates.confirmation)

@dp.message(PaymentStates.confirmation, F.text == "💰 Оплатить CryptoBot")
async def deposit_with_cryptobot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    rub_amount = Decimal(str(data['amount']))
    usdt_amount = await convert_rub_to_usdt(rub_amount)
    user_id = message.from_user.id
    
    if usdt_amount < Decimal('1.00'):
        await message.answer(
            f"❌ Минимальная сумма 1 USDT (~{USDT_RATE} руб)\n"
            f"Ваша сумма: {usdt_amount} USDT",
            reply_markup=get_back_kb()
        )
        return
    
    # Сохраняем данные о пополнении
    temp_deposits[user_id] = {
        'rub_amount': rub_amount,
        'usdt_amount': usdt_amount,
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "asset": "USDT",
        "amount": str(usdt_amount),
        "description": f"Пополнение баланса на {rub_amount} руб",
        "payload": f"deposit_{user_id}",
        "allow_anonymous": False
    }
    
    try:
        response = requests.post(f"{CRYPTO_BOT_API_URL}/createInvoice", headers=headers, json=payload)
        response.raise_for_status()
        invoice = response.json()['result']
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить сейчас", url=invoice['pay_url'])],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_deposit_{invoice['invoice_id']}")]
        ])
        
        await message.answer(
            f"💎 <b>Пополнение баланса</b>\n\n"
            f"▫️ Сумма: <b>{rub_amount} руб</b>\n"
            f"▫️ В USDT: <b>{usdt_amount}</b>\n"
            f"▫️ Курс: 1 USDT = {USDT_RATE} руб\n\n"
            "⏳ Счет действителен <b>15 минут</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )
        
        asyncio.create_task(check_deposit_payment(invoice['invoice_id'], user_id, rub_amount, usdt_amount))
        
    except Exception as e:
        logger.error(f"CryptoBot deposit error: {e}")
        await message.answer(
            "⚠ Произошла ошибка при создании счета. Попробуйте позже.",
            reply_markup=get_back_kb()
        )

async def check_deposit_payment(invoice_id, user_id, rub_amount, usdt_amount):
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    
    for _ in range(30):  # Проверяем в течение 15 минут
        await asyncio.sleep(30)
        try:
            response = requests.get(f"{CRYPTO_BOT_API_URL}/getInvoices?invoice_ids={invoice_id}", headers=headers)
            response.raise_for_status()
            invoice = response.json()['result']['items'][0]
            
            if invoice['status'] == 'paid' and user_id in temp_deposits:
                db = load_db()
                user_id_str = str(user_id)
                
                # Пополняем баланс
                current_balance = Decimal(db['users'].get(user_id_str, {}).get('balance', '0'))
                db['users'].setdefault(user_id_str, {
                    'balance': 0,
                    'orders': [],
                    'username': (await bot.get_chat(user_id)).username
                })
                
                db['users'][user_id_str]['balance'] = str(current_balance + rub_amount)
                save_db(db)
                
                # Удаляем из временного хранилища
                del temp_deposits[user_id]
                
                # Уведомляем пользователя
                await bot.send_message(
                    user_id,
                    f"✅ <b>Баланс успешно пополнен!</b>\n\n"
                    f"▫️ Сумма: {rub_amount} руб\n"
                    f"▫️ В USDT: {usdt_amount}\n"
                    f"▫️ Новый баланс: {current_balance + rub_amount} руб",
                    reply_markup=get_main_kb(user_id),
                    parse_mode="HTML"
                )
                return
                
        except Exception as e:
            logger.error(f"Deposit check error: {e}")
    
    # Если оплата не прошла
    if user_id in temp_deposits:
        await bot.send_message(
            user_id,
            "⌛ Время на оплату истекло. Если вы уже оплатили, свяжитесь с поддержкой.",
            reply_markup=get_main_kb(user_id)
        )
        del temp_deposits[user_id]

@dp.callback_query(F.data.startswith("check_deposit_"))
async def check_deposit_handler(callback: types.CallbackQuery):
    invoice_id = callback.data.split("_")[2]
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    
    try:
        response = requests.get(f"{CRYPTO_BOT_API_URL}/getInvoices?invoice_ids={invoice_id}", headers=headers)
        response.raise_for_status()
        invoice = response.json()['result']['items'][0]
        
        if invoice['status'] == 'paid':
            await callback.answer("✅ Оплата уже зачислена!", show_alert=True)
        else:
            await callback.answer("ℹ️ Оплата еще не поступила", show_alert=True)
    except Exception as e:
        logger.error(f"Deposit check error: {e}")
        await callback.answer("⚠ Ошибка проверки, попробуйте позже", show_alert=True)

# Поддержка
@dp.message(F.text == "🆘 Поддержка")
async def cmd_support(message: types.Message):
    support_text = f"""
🆘 <b>Поддержка</b>

По всем вопросам:
• Напишите нам: {SUPPORT_USERNAME}
• Или на email: support@example.com

⏳ Время ответа: 10:00-20:00 (МСК)
    """
    await message.answer(support_text, parse_mode="HTML", reply_markup=get_back_kb())

# =============================================
# АДМИН-ПАНЕЛЬ (полная реализация)
# =============================================

@dp.message(F.text == "👑 Админ")
async def cmd_admin(message: types.Message):
    db = load_db()
    user_id = message.from_user.id
    
    if user_id not in db['admins']:
        await message.answer("❌ У вас нет доступа к админ-панели")
        return
    
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="📊 Статистика бота"))
    kb.add(KeyboardButton(text="📦 Управление заказами"))
    kb.add(KeyboardButton(text="👥 Список админов"))
    kb.add(KeyboardButton(text="➕ Добавить админа"))
    kb.add(KeyboardButton(text="➖ Удалить админа"))
    kb.add(KeyboardButton(text="💰 Изменить баланс"))
    kb.add(KeyboardButton(text="🔙 В главное меню"))
    kb.adjust(2)
    
    await message.answer(
        "👑 <b>Административная панель</b>\n\n"
        "Выберите действие:",
        reply_markup=kb.as_markup(resize_keyboard=True),
        parse_mode="HTML"
    )

@dp.message(F.text == "📊 Статистика бота")
async def show_bot_stats(message: types.Message):
    db = load_db()
    
    stats = {
        "users": len(db['users']),
        "orders": len(db['orders']),
        "paid_orders": sum(1 for o in db['orders'].values() if o['status'] == 'paid'),
        "revenue": sum(float(o['amount']) for o in db['orders'].values() if o['status'] == 'paid'),
        "admins": len(db['admins'])
    }
    
    text = (
        "📈 <b>Статистика бота</b>\n\n"
        f"👤 Пользователей: <b>{stats['users']}</b>\n"
        f"📦 Всего заказов: <b>{stats['orders']}</b>\n"
        f"💰 Оплаченных заказов: <b>{stats['paid_orders']}</b>\n"
        f"💵 Общая выручка: <b>{stats['revenue']:.2f} руб</b>\n"
        f"👑 Администраторов: <b>{stats['admins']}</b>\n\n"
        f"🔄 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "📦 Управление заказами")
async def manage_orders(message: types.Message, state: FSMContext):
    db = load_db()
    
    if not db['orders']:
        await message.answer("❌ Нет заказов для управления")
        return
    
    # Получаем последние 10 заказов
    last_orders = sorted(
        [(k, v) for k, v in db['orders'].items()],
        key=lambda x: x[1]['created_at'],
        reverse=True
    )[:10]
    
    kb = InlineKeyboardBuilder()
    for order_id, order in last_orders:
        status_icon = "✅" if order['status'] == 'paid' else "🔄"
        kb.add(InlineKeyboardButton(
            text=f"{status_icon} #{order_id} - {order['service']}",
            callback_data=f"admin_order_{order_id}"
        ))
    kb.adjust(1)
    
    await message.answer(
        "📦 <b>Управление заказами</b>\n\n"
        "Выберите заказ для управления:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.managing_orders)

@dp.callback_query(F.data.startswith("admin_order_"), AdminStates.managing_orders)
async def process_order_management(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[2]
    db = load_db()
    order = db['orders'].get(order_id)
    
    if not order:
        await callback.answer("Заказ не найден!")
        return
    
    user = db['users'].get(str(order['user_id']), {})
    status_icons = {
        'paid': '✅ Оплачен',
        'completed': '🏁 Завершен',
        'rejected': '❌ Отклонен',
        'pending': '⏳ Ожидает'
    }
    
    text = (
        f"📦 <b>Заказ #{order_id}</b>\n\n"
        f"👤 Пользователь: @{user.get('username', 'N/A')} (ID: {order['user_id']})\n"
        f"🛒 Услуга: {order['service']}\n"
        f"🖥 Платформа: {order['platform']}\n"
        f"📺 Канал: {order['channel']}\n"
        f"📅 Дата: {order['date']} в {order['time']}\n"
        f"💰 Сумма: {order['amount']} руб\n"
        f"📌 Статус: {status_icons.get(order['status'], order['status'])}\n"
        f"🕒 Создан: {order['created_at']}"
    )
    
    kb = InlineKeyboardBuilder()
    
    if order['status'] == 'paid':
        kb.add(InlineKeyboardButton(text="✅ Завершить", callback_data=f"complete_{order_id}"))
        kb.add(InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order_id}"))
    elif order['status'] == 'completed':
        kb.add(InlineKeyboardButton(text="🔄 Вернуть в работу", callback_data=f"return_{order_id}"))
    
    kb.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_orders"))
    kb.adjust(2)
    
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith(("complete_", "reject_", "return_")))
async def change_order_status(callback: types.CallbackQuery):
    action, order_id = callback.data.split("_")
    db = load_db()
    order = db['orders'].get(order_id)
    
    if not order:
        await callback.answer("Заказ не найден!")
        return
    
    status_map = {
        "complete": "completed",
        "reject": "rejected",
        "return": "paid"
    }
    
    new_status = status_map[action]
    order['status'] = new_status
    order['processed_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_db(db)
    
    # Уведомляем пользователя
    status_messages = {
        "completed": f"✅ Ваш заказ #{order_id} успешно выполнен!",
        "rejected": f"❌ Ваш заказ #{order_id} отклонен. Подробности у поддержки.",
        "paid": f"🔄 Ваш заказ #{order_id} возвращен в работу."
    }
    
    try:
        await bot.send_message(order['user_id'], status_messages[new_status])
    except:
        pass
    
    await callback.answer(f"Статус заказа #{order_id} изменен на {new_status}")
    await manage_orders(callback.message, callback.message.from_user.id)

@dp.message(F.text == "👥 Список админов")
async def show_admins(message: types.Message):
    db = load_db()
    
    if not db['admins']:
        await message.answer("❌ Нет администраторов")
        return
    
    text = "👑 <b>Список администраторов</b>\n\n"
    for admin_id in db['admins']:
        try:
            user = await bot.get_chat(admin_id)
            text += f"• @{user.username} (ID: {admin_id})\n"
        except:
            text += f"• ID: {admin_id} (нет доступа)\n"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "➕ Добавить админа")
async def add_admin_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите ID пользователя, которого хотите сделать администратором:",
        reply_markup=get_back_kb()
    )
    await state.set_state(AdminStates.adding_admin)

@dp.message(AdminStates.adding_admin, F.text.regexp(r'^\d+$'))
async def add_admin_process(message: types.Message, state: FSMContext):
    db = load_db()
    new_admin_id = int(message.text)
    
    if new_admin_id in db['admins']:
        await message.answer("❌ Этот пользователь уже является администратором")
        return
    
    db['admins'].append(new_admin_id)
    save_db(db)
    
    try:
        user = await bot.get_chat(new_admin_id)
        await message.answer(f"✅ Пользователь @{user.username} (ID: {new_admin_id}) добавлен в администраторы")
    except:
        await message.answer(f"✅ Пользователь с ID {new_admin_id} добавлен в администраторы")
    
    await state.clear()
    await cmd_admin(message)

@dp.message(F.text == "➖ Удалить админа")
async def remove_admin_start(message: types.Message, state: FSMContext):
    db = load_db()
    
    if len(db['admins']) <= 1:
        await message.answer("❌ Нельзя удалить последнего администратора!")
        return
    
    kb = ReplyKeyboardBuilder()
    for admin_id in db['admins']:
        if admin_id != message.from_user.id:  # Нельзя удалить себя
            kb.add(KeyboardButton(text=str(admin_id)))
    kb.add(KeyboardButton(text="🔙 Назад"))
    kb.adjust(2)
    
    await message.answer(
        "Выберите ID администратора для удаления:",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(AdminStates.removing_admin)

@dp.message(AdminStates.removing_admin, F.text.regexp(r'^\d+$'))
async def remove_admin_process(message: types.Message, state: FSMContext):
    db = load_db()
    admin_id = int(message.text)
    
    if admin_id not in db['admins']:
        await message.answer("❌ Этот пользователь не является администратором")
        return
    
    if admin_id == message.from_user.id:
        await message.answer("❌ Вы не можете удалить сами себя")
        return
    
    db['admins'].remove(admin_id)
    save_db(db)
    
    try:
        user = await bot.get_chat(admin_id)
        await message.answer(f"✅ Пользователь @{user.username} (ID: {admin_id}) удален из администраторов")
    except:
        await message.answer(f"✅ Пользователь с ID {admin_id} удален из администраторов")
    
    await state.clear()
    await cmd_admin(message)

@dp.message(F.text == "💰 Изменить баланс")
async def change_balance_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите ID пользователя и сумму через пробел (например: <code>123456789 500</code> для пополнения или <code>123456789 -300</code> для списания):",
        reply_markup=get_back_kb(),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.changing_balance)

@dp.message(F.text == "🔙 В главное меню")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Главное меню", reply_markup=get_main_kb(message.from_user.id))
    
@dp.message(AdminStates.changing_balance, F.text.regexp(r'^\d+\s+-?\d+$'))
async def change_balance_process(message: types.Message, state: FSMContext):
    user_id, amount = message.text.split()
    user_id = int(user_id)
    amount = int(amount)
    
    db = load_db()
    user_id_str = str(user_id)
    
    if user_id_str not in db['users']:
        await message.answer("❌ Пользователь не найден")
        return
    
    current_balance = int(db['users'][user_id_str]['balance'])
    new_balance = current_balance + amount
    
    if new_balance < 0:
        await message.answer("❌ Нельзя установить отрицательный баланс")
        return
    
    db['users'][user_id_str]['balance'] = new_balance
    save_db(db)
    
    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f"ℹ️ Ваш баланс был изменен администратором\n"
            f"Изменение: {'+' if amount >= 0 else ''}{amount} руб\n"
            f"Новый баланс: {new_balance} руб"
        )
    except:
        pass
    
    await message.answer(
        f"✅ Баланс пользователя {user_id} изменен\n"
        f"Старый баланс: {current_balance} руб\n"
        f"Изменение: {'+' if amount >= 0 else ''}{amount} руб\n"
        f"Новый баланс: {new_balance} руб"
    )
    
    await state.clear()
    await cmd_admin(message)

import asyncio
import sys
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO)

# Фейковый веб-сервер, чтобы Render не убивал процесс
def run_fake_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

async def main():
    try:
        run_fake_server()  # запускаем фейковый сервер
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logging.exception("❌ Ошибка в main, бот будет перезапущен")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("⏹️ Бот остановлен вручную")
