from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def specialists_keyboard(barbers: list[str]):
    keyboard = [
        [InlineKeyboardButton(text=barber, callback_data=f"show_barber:{barber}")]
        for barber in barbers
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def main_keyboard(is_admin: bool = False):
    keyboard = [
        [KeyboardButton(text="✂️ Записаться")],
        [KeyboardButton(text="💈 Услуги и цены"), KeyboardButton(text="📍 Адрес")],
        [KeyboardButton(text="👨‍🔧 Специалисты"), KeyboardButton(text="❌ Отменить запись")],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер", request_contact=True)],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def barbers_keyboard(barbers: list[str]):
    keyboard = [[KeyboardButton(text=barber)] for barber in barbers]
    keyboard.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def services_keyboard(services: list[str]):
    keyboard = [[KeyboardButton(text=service)] for service in services]
    keyboard.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def dates_keyboard(dates: list[str]):
    keyboard = [[KeyboardButton(text=date)] for date in dates]
    keyboard.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def times_keyboard(times: list[str]):
    keyboard = [[KeyboardButton(text=time)] for time in times]
    keyboard.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Записи на сегодня")],
            [KeyboardButton(text="📚 Последние записи")],
            [KeyboardButton(text="📖 История записей")],
            [KeyboardButton(text="🗑 Отменить запись (админ)")],
            [KeyboardButton(text="👨‍🔧 Управление барберами")],
            [KeyboardButton(text="📢 Рассылка клиентам")],
            [KeyboardButton(text="🏠 В меню")]
        ],
        resize_keyboard=True
    )


# ---- Клиентская отмена ----

def cancel_bookings_keyboard(bookings: list) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура со списком активных записей клиента для отмены."""
    keyboard = []
    for b in bookings:
        label = f"❌ {b['booking_date']} {b['booking_time']} — {b['barber']} ({b['service']})"
        keyboard.append([
            InlineKeyboardButton(text=label, callback_data=f"cancel_booking:{b['id']}")
        ])
    keyboard.append([
        InlineKeyboardButton(text="🔙 Закрыть", callback_data="cancel_booking:close")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def confirm_cancel_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения отмены для клиента."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, отменить", callback_data=f"confirm_cancel:{booking_id}"),
            InlineKeyboardButton(text="🔙 Нет, назад", callback_data="cancel_booking:back"),
        ]
    ])


# ---- Админская отмена ----

def admin_cancel_bookings_keyboard(bookings: list) -> InlineKeyboardMarkup:
    """Инлайн-клавиатура всех активных записей для админа."""
    keyboard = []
    for b in bookings:
        label = (
            f"🗑 #{b['id']} {b['booking_date']} {b['booking_time']} "
            f"— {b['client_name']} | {b['barber']}"
        )
        keyboard.append([
            InlineKeyboardButton(text=label, callback_data=f"admin_cancel:{b['id']}")
        ])
    keyboard.append([
        InlineKeyboardButton(text="🔙 Закрыть", callback_data="admin_cancel:close")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_confirm_cancel_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Подтверждение отмены для админа."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отменить запись", callback_data=f"admin_confirm_cancel:{booking_id}"),
            InlineKeyboardButton(text="🔙 Назад к списку", callback_data="admin_cancel:back"),
        ]
    ])
