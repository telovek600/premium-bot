import re
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import (
    ADMIN_IDS,
    BARBERSHOP_NAME,
    ADDRESS,
    CONTACTS,
    SERVICES,
    BOOKING_DAYS_AHEAD,
    TIME_SLOT_STEP_MINUTES,
)

from database import (
    get_barbers,
    get_barber,
    get_barber_names,
    add_barber,
    delete_barber,
    upsert_client,
    create_booking,
    get_bookings_for_barber_date,
    get_today_bookings,
    get_recent_bookings,
    get_all_clients,
    get_active_bookings_for_user,
    get_all_active_bookings,
    get_booking_by_id,
    cancel_booking,
    get_booking_history,
)

from keyboards import (
    main_keyboard,
    phone_keyboard,
    barbers_keyboard,
    services_keyboard,
    dates_keyboard,
    times_keyboard,
    admin_keyboard,
    specialists_keyboard,
    cancel_bookings_keyboard,
    confirm_cancel_keyboard,
    admin_cancel_bookings_keyboard,
    admin_confirm_cancel_keyboard,
)

from scheduler_jobs import schedule_booking_reminder
from states import BookingState, AdminState, BarberAdminState

router = Router()


# ------------------------------------------------
# UTILS
# ------------------------------------------------

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def format_date_label(date_obj: datetime) -> str:
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    return f"{date_obj.strftime('%d.%m.%Y')} ({weekdays[date_obj.weekday()]})"


def parse_date_label(label: str) -> str:
    return label.split(" ")[0]


def to_iso_date(date_str: str) -> str:
    return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")


def time_to_minutes(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m


def minutes_to_time(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def has_overlap(start1: int, dur1: int, start2: int, dur2: int) -> bool:
    end1 = start1 + dur1
    end2 = start2 + dur2
    return max(start1, start2) < min(end1, end2)


# ------------------------------------------------
# BARBER CARD
# ------------------------------------------------

@router.callback_query(F.data.startswith("show_barber:"))
async def show_barber_card(callback: CallbackQuery):
    barber_name = callback.data.split(":")[1]
    barber = get_barber(barber_name)

    if not barber:
        await callback.answer("Барбер не найден", show_alert=True)
        return

    text = (
        f"💈 <b>{barber['name']}</b>\n\n"
        f"📅 Стаж: {barber['experience']}\n"
        f"✂️ Специализация: {barber['specialization']}\n"
        f"🔥 Сильные стороны: {barber['strong_sides']}\n\n"
        f"{barber['description']}"
    )

    await callback.message.answer_photo(
        photo=barber["photo"],
        caption=text,
        parse_mode="HTML"
    )
    await callback.answer()


# ------------------------------------------------
# AVAILABLE DATES / FREE TIMES
# ------------------------------------------------

def generate_available_dates(barber_name: str) -> list:
    barber = get_barber(barber_name)
    if not barber:
        return []
    try:
        workdays = list(map(int, barber["workdays"].split(",")))
    except Exception:
        workdays = [0, 1, 2, 3, 4, 5, 6]

    today = datetime.now()
    result = []
    for i in range(BOOKING_DAYS_AHEAD):
        day = today + timedelta(days=i)
        if day.weekday() in workdays:
            result.append(format_date_label(day))
    return result


def generate_free_times(barber_name: str, booking_date: str, duration: int) -> list:
    barber = get_barber(barber_name)
    if not barber:
        return []
    try:
        start_time = barber["start_time"] or "10:00"
        end_time = barber["end_time"] or "20:00"
    except Exception:
        start_time = "10:00"
        end_time = "20:00"

    work_start = time_to_minutes(start_time)
    work_end = time_to_minutes(end_time)

    # Если запись на сегодня — не показываем уже прошедшее время
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    if booking_date == today_str:
        now_minutes = now.hour * 60 + now.minute
        work_start = max(work_start, now_minutes)

    existing = get_bookings_for_barber_date(barber_name, booking_date)
    existing_slots = [
        (time_to_minutes(row["booking_time"]), row["duration_min"])
        for row in existing
    ]

    free = []
    current = work_start
    while current + duration <= work_end:
        busy = any(
            has_overlap(current, duration, s, d)
            for s, d in existing_slots
        )
        if not busy:
            free.append(minutes_to_time(current))
        current += TIME_SLOT_STEP_MINUTES
    return free


# ------------------------------------------------
# START
# ------------------------------------------------

@router.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Добро пожаловать в {BARBERSHOP_NAME} 💈",
        reply_markup=main_keyboard(is_admin(message.from_user.id))
    )


# ------------------------------------------------
# SPECIALISTS
# ------------------------------------------------

@router.message(F.text == "👨‍🔧 Специалисты")
async def show_specialists(message: Message):
    barbers = get_barbers()
    if not barbers:
        await message.answer("Список барберов пуст")
        return
    names = [b["name"] for b in barbers]
    await message.answer("Наши специалисты:", reply_markup=specialists_keyboard(names))


# ------------------------------------------------
# КЛИЕНТ — ОТМЕНА СВОЕЙ ЗАПИСИ
# ------------------------------------------------

@router.message(F.text == "❌ Отменить запись")
async def show_my_bookings(message: Message):
    bookings = get_active_bookings_for_user(message.from_user.id)
    if not bookings:
        await message.answer(
            "У вас нет активных записей.",
            reply_markup=main_keyboard(is_admin(message.from_user.id))
        )
        return
    await message.answer(
        "Ваши активные записи.\nНажмите на запись чтобы отменить:",
        reply_markup=cancel_bookings_keyboard(bookings)
    )


@router.callback_query(F.data.startswith("cancel_booking:"))
async def handle_cancel_booking(callback: CallbackQuery):
    action = callback.data.split(":")[1]

    if action == "close":
        await callback.message.delete()
        await callback.answer()
        return

    if action == "back":
        bookings = get_active_bookings_for_user(callback.from_user.id)
        if not bookings:
            await callback.message.edit_text("У вас нет активных записей.")
        else:
            await callback.message.edit_reply_markup(
                reply_markup=cancel_bookings_keyboard(bookings)
            )
        await callback.answer()
        return

    try:
        booking_id = int(action)
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    booking = get_booking_by_id(booking_id)

    if not booking:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    if booking["user_id"] != callback.from_user.id:
        await callback.answer("Это не ваша запись", show_alert=True)
        return
    if booking["status"] != "active":
        await callback.answer("Запись уже отменена", show_alert=True)
        return

    text = (
        f"Вы уверены, что хотите отменить запись?\n\n"
        f"💈 Мастер: {booking['barber']}\n"
        f"✂️ Услуга: {booking['service']}\n"
        f"📅 Дата: {booking['booking_date']}\n"
        f"🕒 Время: {booking['booking_time']}"
    )
    await callback.message.edit_text(text, reply_markup=confirm_cancel_keyboard(booking_id))
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_cancel:"))
async def handle_confirm_cancel(callback: CallbackQuery):
    try:
        booking_id = int(callback.data.split(":")[1])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    booking = get_booking_by_id(booking_id)

    if not booking or booking["user_id"] != callback.from_user.id:
        await callback.answer("Ошибка", show_alert=True)
        return
    if booking["status"] != "active":
        await callback.message.edit_text("Эта запись уже была отменена.")
        await callback.answer()
        return

    cancel_booking(booking_id)

    # Уведомляем всех админов
    for admin_id in ADMIN_IDS:
        try:
            await callback.bot.send_message(
                admin_id,
                f"❌ Клиент отменил запись!\n\n"
                f"👤 {booking['client_name']} | 📞 {booking['phone']}\n"
                f"💈 Мастер: {booking['barber']}\n"
                f"✂️ Услуга: {booking['service']}\n"
                f"📅 {booking['booking_date']} в {booking['booking_time']}"
            )
        except Exception:
            pass

    await callback.message.edit_text(
        f"✅ Запись отменена.\n\n"
        f"💈 {booking['barber']} | ✂️ {booking['service']}\n"
        f"📅 {booking['booking_date']} в {booking['booking_time']}\n\n"
        "Будем рады видеть вас снова!"
    )
    await callback.answer("Запись отменена", show_alert=True)


# ------------------------------------------------
# АДМИН — ОТМЕНА ЛЮБОЙ ЗАПИСИ ЧЕРЕЗ КНОПКИ
# ------------------------------------------------

@router.message(F.text == "🗑 Отменить запись (админ)")
async def admin_show_all_bookings(message: Message):
    if not is_admin(message.from_user.id):
        return

    bookings = get_all_active_bookings()

    if not bookings:
        await message.answer("Активных записей нет.", reply_markup=admin_keyboard())
        return

    await message.answer(
        f"Активные записи ({len(bookings)} шт.).\nНажмите на запись чтобы отменить:",
        reply_markup=admin_cancel_bookings_keyboard(bookings)
    )


@router.callback_query(F.data.startswith("admin_cancel:"))
async def handle_admin_cancel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    action = callback.data.split(":")[1]

    if action == "close":
        await callback.message.delete()
        await callback.answer()
        return

    if action == "back":
        bookings = get_all_active_bookings()
        if not bookings:
            await callback.message.edit_text("Активных записей нет.")
        else:
            await callback.message.edit_reply_markup(
                reply_markup=admin_cancel_bookings_keyboard(bookings)
            )
        await callback.answer()
        return

    try:
        booking_id = int(action)
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    booking = get_booking_by_id(booking_id)

    if not booking:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    if booking["status"] != "active":
        await callback.answer("Запись уже отменена", show_alert=True)
        return

    text = (
        f"Отменить эту запись?\n\n"
        f"#{booking['id']} | 👤 {booking['client_name']}\n"
        f"📞 {booking['phone']}\n"
        f"💈 Мастер: {booking['barber']}\n"
        f"✂️ Услуга: {booking['service']}\n"
        f"📅 {booking['booking_date']} в {booking['booking_time']}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_confirm_cancel_keyboard(booking_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_cancel:"))
async def handle_admin_confirm_cancel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    try:
        booking_id = int(callback.data.split(":")[1])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    booking = get_booking_by_id(booking_id)

    if not booking:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    if booking["status"] != "active":
        await callback.message.edit_text("Эта запись уже была отменена.")
        await callback.answer()
        return

    cancel_booking(booking_id)

    # Уведомляем клиента
    try:
        await callback.bot.send_message(
            booking["user_id"],
            f"❌ Ваша запись была отменена администратором.\n\n"
            f"💈 Мастер: {booking['barber']}\n"
            f"✂️ Услуга: {booking['service']}\n"
            f"📅 {booking['booking_date']} в {booking['booking_time']}\n\n"
            "Для повторной записи нажмите ✂️ Записаться"
        )
    except Exception:
        pass

    await callback.message.edit_text(
        f"✅ Запись #{booking_id} отменена.\n"
        f"👤 {booking['client_name']} уведомлён."
    )
    await callback.answer("Запись отменена", show_alert=True)


# ------------------------------------------------
# BACK BUTTON
# ------------------------------------------------

@router.message(F.text == "⬅️ Назад")
async def go_back(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state == BookingState.phone.state:
        await state.set_state(BookingState.name)
        await message.answer("Как вас зовут?")
    elif current_state == BookingState.barber.state:
        await state.set_state(BookingState.phone)
        await message.answer("Введите номер телефона:", reply_markup=phone_keyboard())
    elif current_state == BookingState.service.state:
        await state.set_state(BookingState.barber)
        await message.answer("Выберите мастера:", reply_markup=barbers_keyboard(get_barber_names()))
    elif current_state == BookingState.date.state:
        await state.set_state(BookingState.service)
        await message.answer("Выберите услугу:", reply_markup=services_keyboard(list(SERVICES.keys())))
    elif current_state == BookingState.time.state:
        data = await state.get_data()
        dates = generate_available_dates(data.get("barber", ""))
        await state.set_state(BookingState.date)
        await message.answer("Выберите дату:", reply_markup=dates_keyboard(dates))
    elif current_state and current_state.startswith("BarberAdminState"):
        await state.clear()
        await message.answer("🛠 Админ-панель:", reply_markup=admin_keyboard())
    elif current_state == AdminState.broadcast_text.state:
        await state.clear()
        await message.answer("🛠 Админ-панель:", reply_markup=admin_keyboard())
    else:
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_keyboard(is_admin(message.from_user.id)))


# ------------------------------------------------
# BOOKING
# ------------------------------------------------

@router.message(F.text == "✂️ Записаться")
async def start_booking(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Как вас зовут?")
    await state.set_state(BookingState.name)


@router.message(BookingState.name)
async def get_name(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await go_back(message, state)
        return
    await state.update_data(client_name=message.text)
    await message.answer("Введите номер телефона:", reply_markup=phone_keyboard())
    await state.set_state(BookingState.phone)


@router.message(BookingState.phone, F.contact)
async def get_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await message.answer("Выберите мастера:", reply_markup=barbers_keyboard(get_barber_names()))
    await state.set_state(BookingState.barber)


@router.message(BookingState.phone, F.text)
async def get_phone_text(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await go_back(message, state)
        return
    phone = message.text.strip()
    if not re.match(r'^(\+7|7|8)\d{10}$', phone):
        await message.answer("Введите номер в формате:\n+79991234567")
        return
    await state.update_data(phone=phone)
    await message.answer("Выберите мастера:", reply_markup=barbers_keyboard(get_barber_names()))
    await state.set_state(BookingState.barber)


@router.message(BookingState.barber)
async def select_barber(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await go_back(message, state)
        return
    names = get_barber_names()
    if message.text not in names:
        await message.answer("Выберите мастера кнопкой", reply_markup=barbers_keyboard(names))
        return
    await state.update_data(barber=message.text)
    await message.answer("Выберите услугу:", reply_markup=services_keyboard(list(SERVICES.keys())))
    await state.set_state(BookingState.service)


@router.message(BookingState.service)
async def get_service(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await go_back(message, state)
        return
    if message.text not in SERVICES:
        await message.answer("Выберите услугу", reply_markup=services_keyboard(list(SERVICES.keys())))
        return
    await state.update_data(service=message.text)
    data = await state.get_data()
    dates = generate_available_dates(data["barber"])
    await message.answer("Выберите дату:", reply_markup=dates_keyboard(dates))
    await state.set_state(BookingState.date)


@router.message(BookingState.date)
async def get_date(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await go_back(message, state)
        return
    data = await state.get_data()
    valid_dates = generate_available_dates(data["barber"])
    if message.text not in valid_dates:
        await message.answer("Выберите дату", reply_markup=dates_keyboard(valid_dates))
        return
    booking_date = parse_date_label(message.text)
    duration = SERVICES[data["service"]]["duration"]
    free_times = generate_free_times(data["barber"], booking_date, duration)
    if not free_times:
        await message.answer("На этот день нет свободного времени, выберите другой.", reply_markup=dates_keyboard(valid_dates))
        return
    await state.update_data(date=booking_date)
    await message.answer("Выберите время:", reply_markup=times_keyboard(free_times))
    await state.set_state(BookingState.time)


@router.message(BookingState.time)
async def get_time(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await go_back(message, state)
        return
    data = await state.get_data()
    service = data["service"]
    barber = data["barber"]
    booking_date = data["date"]
    duration = SERVICES[service]["duration"]
    free_times = generate_free_times(barber, booking_date, duration)
    if message.text not in free_times:
        await message.answer("Выберите время кнопкой", reply_markup=times_keyboard(free_times))
        return

    booking_time = message.text
    iso_date = to_iso_date(booking_date)
    appointment_at = f"{iso_date}T{booking_time}:00"

    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    client_name = data["client_name"]
    phone = data["phone"]
    service_price = SERVICES[service]["price"]

    upsert_client(user_id=user_id, client_name=client_name, phone=phone, username=username, full_name=full_name)

    booking_id = create_booking(
        user_id=user_id, client_name=client_name, phone=phone,
        barber=barber, service=service, service_price=service_price,
        duration_min=duration, booking_date=booking_date,
        booking_time=booking_time, appointment_at=appointment_at
    )

    schedule_booking_reminder(
        booking_id=booking_id, user_id=user_id, barber=barber,
        service=service, booking_date=booking_date,
        booking_time=booking_time, appointment_at=appointment_at
    )

    await message.answer(
        "✅ Вы успешно записаны!\n\n"
        f"👤 Имя: {client_name}\n"
        f"📞 Телефон: {phone}\n"
        f"💈 Мастер: {barber}\n"
        f"✂️ Услуга: {service}\n"
        f"💵 Цена: {service_price} ₽\n"
        f"📅 Дата: {booking_date}\n"
        f"🕒 Время: {booking_time}\n\n"
        "Мы ждём вас!",
        reply_markup=main_keyboard(is_admin(user_id))
    )
    await state.clear()


# ------------------------------------------------
# ADDRESS / SERVICES
# ------------------------------------------------

@router.message(F.text == "📍 Адрес")
async def show_address(message: Message):
    await message.answer(
        f"📍 Адрес: {ADDRESS}\n📞 Контакты: {CONTACTS}",
        reply_markup=main_keyboard(is_admin(message.from_user.id))
    )


@router.message(F.text == "💈 Услуги и цены")
async def show_services(message: Message):
    text = "💈 Услуги и цены:\n\n"
    for service_name, info in SERVICES.items():
        text += f"• {service_name} — {info['price']} ₽ ({info['duration']} мин)\n"
    await message.answer(text, reply_markup=main_keyboard(is_admin(message.from_user.id)))


# ------------------------------------------------
# ADMIN PANEL
# ------------------------------------------------

@router.message(F.text == "🛠 Админ-панель")
@router.message(Command("admin"))
async def open_admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return
    await state.clear()
    await message.answer("🛠 Админ-панель\n\nВыберите действие:", reply_markup=admin_keyboard())


@router.message(F.text == "📅 Записи на сегодня")
async def admin_today_bookings(message: Message):
    if not is_admin(message.from_user.id):
        return
    today = datetime.now().strftime("%d.%m.%Y")
    bookings = get_today_bookings(today)
    if not bookings:
        await message.answer("📅 На сегодня записей нет.", reply_markup=admin_keyboard())
        return
    text = f"📅 Записи на сегодня ({today}):\n\n"
    for b in bookings:
        text += (
            f"🕒 {b['booking_time']} — {b['client_name']}\n"
            f"   💈 {b['barber']} | ✂️ {b['service']}\n"
            f"   📞 {b['phone']} | #{b['id']}\n\n"
        )
    await message.answer(text, reply_markup=admin_keyboard())


@router.message(F.text == "📚 Последние записи")
async def admin_recent_bookings(message: Message):
    if not is_admin(message.from_user.id):
        return
    bookings = get_recent_bookings(15)
    if not bookings:
        await message.answer("📚 Записей пока нет.", reply_markup=admin_keyboard())
        return
    text = "📚 Последние 15 записей:\n\n"
    for b in bookings:
        icon = "✅" if b['status'] == 'active' else "❌"
        text += (
            f"{icon} #{b['id']} {b['booking_date']} {b['booking_time']}\n"
            f"   👤 {b['client_name']} | 📞 {b['phone']}\n"
            f"   💈 {b['barber']} | ✂️ {b['service']}\n\n"
        )
    await message.answer(text, reply_markup=admin_keyboard())


@router.message(F.text == "📖 История записей")
async def admin_booking_history(message: Message):
    if not is_admin(message.from_user.id):
        return
    bookings = get_booking_history(50)
    if not bookings:
        await message.answer(
            "📖 История пока пуста.\n\nЗдесь будут появляться завершённые и отменённые записи.",
            reply_markup=admin_keyboard()
        )
        return

    completed = [b for b in bookings if b['status'] == 'completed']
    cancelled = [b for b in bookings if b['status'] == 'cancelled']

    text = f"📖 История записей (последние 50)\n\n"
    text += f"✅ Завершённых: {len(completed)}  ❌ Отменённых: {len(cancelled)}\n"
    text += "─" * 30 + "\n\n"

    for b in bookings:
        if b['status'] == 'completed':
            icon = "✅"
            status_label = "завершена"
        else:
            icon = "❌"
            status_label = "отменена"

        text += (
            f"{icon} #{b['id']} {b['booking_date']} {b['booking_time']} ({status_label})\n"
            f"   👤 {b['client_name']} | 📞 {b['phone']}\n"
            f"   💈 {b['barber']} | ✂️ {b['service']} | 💵 {b['service_price']} ₽\n\n"
        )

    # Телеграм лимит 4096 символов — режем если длинно
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (показаны последние 50 записей)"

    await message.answer(text, reply_markup=admin_keyboard())


@router.message(F.text == "👨‍🔧 Управление барберами")
async def admin_barbers(message: Message):
    if not is_admin(message.from_user.id):
        return
    barbers = get_barbers()
    text = "👨‍🔧 Барберы:\n\n"
    if barbers:
        for b in barbers:
            text += f"{b['id']}. {b['name']}\n"
    else:
        text += "Список пуст.\n"
    text += "\n/add_barber — добавить\n/delete_barber ID — удалить"
    await message.answer(text, reply_markup=admin_keyboard())


@router.message(Command("delete_barber"))
async def delete_barber_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Используй: /delete_barber ID")
        return
    try:
        barber_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом")
        return
    delete_barber(barber_id)
    await message.answer("✅ Барбер удалён", reply_markup=admin_keyboard())


@router.message(Command("add_barber"))
async def add_barber_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Добавление нового барбера.\n\nВведите имя барбера:")
    await state.set_state(BarberAdminState.name)


@router.message(BarberAdminState.name)
async def barber_admin_name(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.clear()
        await message.answer("🛠 Админ-панель:", reply_markup=admin_keyboard())
        return
    await state.update_data(name=message.text)
    await message.answer("Введите стаж (например: 5 лет):")
    await state.set_state(BarberAdminState.experience)


@router.message(BarberAdminState.experience)
async def barber_admin_experience(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(BarberAdminState.name)
        await message.answer("Введите имя барбера:")
        return
    await state.update_data(experience=message.text)
    await message.answer("Введите специализацию:")
    await state.set_state(BarberAdminState.specialization)


@router.message(BarberAdminState.specialization)
async def barber_admin_specialization(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(BarberAdminState.experience)
        await message.answer("Введите стаж:")
        return
    await state.update_data(specialization=message.text)
    await message.answer("Введите сильные стороны:")
    await state.set_state(BarberAdminState.strong_sides)


@router.message(BarberAdminState.strong_sides)
async def barber_admin_strong_sides(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(BarberAdminState.specialization)
        await message.answer("Введите специализацию:")
        return
    await state.update_data(strong_sides=message.text)
    await message.answer("Введите описание барбера:")
    await state.set_state(BarberAdminState.description)


@router.message(BarberAdminState.description)
async def barber_admin_description(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(BarberAdminState.strong_sides)
        await message.answer("Введите сильные стороны:")
        return
    await state.update_data(description=message.text)
    await message.answer("Отправьте фото барбера или введите file_id фото:")
    await state.set_state(BarberAdminState.photo)


@router.message(BarberAdminState.photo)
async def barber_admin_photo(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.set_state(BarberAdminState.description)
        await message.answer("Введите описание барбера:")
        return
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text:
        photo_id = message.text.strip()
    else:
        await message.answer("Отправьте фото или введите file_id")
        return
    data = await state.get_data()
    add_barber(
        name=data["name"], experience=data["experience"],
        specialization=data["specialization"], strong_sides=data["strong_sides"],
        description=data["description"], photo=photo_id,
    )
    await state.clear()
    await message.answer(f"✅ Барбер {data['name']} успешно добавлен!", reply_markup=admin_keyboard())


@router.message(F.text == "📢 Рассылка клиентам")
async def admin_broadcast_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Введите текст рассылки.\n\n(⬅️ Назад для отмены)")
    await state.set_state(AdminState.broadcast_text)


@router.message(AdminState.broadcast_text)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await state.clear()
        await message.answer("🛠 Админ-панель:", reply_markup=admin_keyboard())
        return
    clients = get_all_clients()
    text = message.text
    sent = 0
    failed = 0
    await message.answer(f"📤 Начинаю рассылку {len(clients)} клиентам...")
    for client in clients:
        try:
            await message.bot.send_message(client["user_id"], text)
            sent += 1
        except Exception:
            failed += 1
    await state.clear()
    await message.answer(
        f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}",
        reply_markup=admin_keyboard()
    )


@router.message(F.text == "🏠 В меню")
async def go_to_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Добро пожаловать в {BARBERSHOP_NAME} 💈",
        reply_markup=main_keyboard(is_admin(message.from_user.id))
    )
