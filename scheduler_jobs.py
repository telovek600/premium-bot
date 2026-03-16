from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from config import TIMEZONE, REMINDER_HOURS_BEFORE
from database import get_future_unreminded_bookings, mark_booking_reminded, archive_expired_bookings

from typing import Optional

scheduler = AsyncIOScheduler(timezone=TIMEZONE)
_bot: Optional[Bot] = None


def set_bot(bot: Bot):
    global _bot
    _bot = bot


async def send_booking_reminder(
    booking_id: int,
    user_id: int,
    barber: str,
    service: str,
    booking_date: str,
    booking_time: str
):
    if _bot is None:
        return

    await _bot.send_message(
        user_id,
        "⏰ Напоминание о записи\n\n"
        f"💈 Мастер: {barber}\n"
        f"✂️ Услуга: {service}\n"
        f"📅 Дата: {booking_date}\n"
        f"🕒 Время: {booking_time}\n\n"
        "Ждём вас в барбершопе!"
    )
    mark_booking_reminded(booking_id)


def schedule_booking_reminder(
    booking_id: int,
    user_id: int,
    barber: str,
    service: str,
    booking_date: str,
    booking_time: str,
    appointment_at: str
):
    appointment_dt = datetime.fromisoformat(appointment_at)
    reminder_dt = appointment_dt - timedelta(hours=REMINDER_HOURS_BEFORE)
    now = datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)

    if reminder_dt <= now:
        return

    scheduler.add_job(
        send_booking_reminder,
        trigger="date",
        run_date=reminder_dt,
        id=f"booking_reminder_{booking_id}",
        replace_existing=True,
        kwargs={
            "booking_id": booking_id,
            "user_id": user_id,
            "barber": barber,
            "service": service,
            "booking_date": booking_date,
            "booking_time": booking_time,
        }
    )


def load_reminders_from_db():
    now_iso = datetime.now().isoformat(timespec="seconds")
    rows = get_future_unreminded_bookings(now_iso)

    for row in rows:
        schedule_booking_reminder(
            booking_id=row["id"],
            user_id=row["user_id"],
            barber=row["barber"],
            service=row["service"],
            booking_date=row["booking_date"],
            booking_time=row["booking_time"],
            appointment_at=row["appointment_at"],
        )

    # Джоб: каждые 5 минут переводить просроченные записи в историю
    if not scheduler.get_job("archive_expired"):
        scheduler.add_job(
            archive_expired_bookings,
            trigger="interval",
            minutes=5,
            id="archive_expired",
            replace_existing=True,
        )