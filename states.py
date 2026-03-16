from aiogram.fsm.state import State, StatesGroup


class BookingState(StatesGroup):
    name = State()
    phone = State()
    barber = State()
    service = State()
    date = State()
    time = State()


class AdminState(StatesGroup):
    broadcast_text = State()


class BarberAdminState(StatesGroup):
    name = State()
    experience = State()
    specialization = State()
    strong_sides = State()
    description = State()
    photo = State()