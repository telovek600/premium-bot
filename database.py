import sqlite3
from datetime import datetime
from typing import Optional

DB_NAME = "barbershop.db"

conn = sqlite3.connect(DB_NAME, check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()


def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        user_id INTEGER PRIMARY KEY,
        client_name TEXT,
        phone TEXT,
        username TEXT,
        full_name TEXT,
        first_seen TEXT,
        last_seen TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        client_name TEXT,
        phone TEXT,
        barber TEXT,
        service TEXT,
        service_price INTEGER,
        duration_min INTEGER,
        booking_date TEXT,
        booking_time TEXT,
        appointment_at TEXT,
        status TEXT DEFAULT 'active',
        reminded INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS barbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        experience TEXT,
        specialization TEXT,
        strong_sides TEXT,
        description TEXT,
        photo TEXT,
        workdays TEXT DEFAULT '0,1,2,3,4,5,6',
        start_time TEXT DEFAULT '10:00',
        end_time TEXT DEFAULT '20:00'
    )
    """)

    # Миграция: добавляем колонки если таблица уже существует без них
    for col, default in [
        ("workdays", "'0,1,2,3,4,5,6'"),
        ("start_time", "'10:00'"),
        ("end_time", "'20:00'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE barbers ADD COLUMN {col} TEXT DEFAULT {default}")
        except Exception:
            pass

    conn.commit()


def upsert_client(
        user_id: int,
        client_name: str,
        phone: str,
        username: Optional[str],
        full_name: Optional[str]
):
    now = datetime.now().isoformat(timespec="seconds")

    existing = cursor.execute(
        "SELECT user_id FROM clients WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    if existing:
        cursor.execute("""
        UPDATE clients
        SET client_name = ?, phone = ?, username = ?, full_name = ?, last_seen = ?
        WHERE user_id = ?
        """, (client_name, phone, username, full_name, now, user_id))
    else:
        cursor.execute("""
        INSERT INTO clients (user_id, client_name, phone, username, full_name, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, client_name, phone, username, full_name, now, now))

    conn.commit()


def create_booking(
        user_id: int,
        client_name: str,
        phone: str,
        barber: str,
        service: str,
        service_price: int,
        duration_min: int,
        booking_date: str,
        booking_time: str,
        appointment_at: str
) -> int:
    created_at = datetime.now().isoformat(timespec="seconds")

    cursor.execute("""
    INSERT INTO bookings (
        user_id, client_name, phone, barber, service, service_price,
        duration_min, booking_date, booking_time, appointment_at, created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, client_name, phone, barber, service, service_price,
        duration_min, booking_date, booking_time, appointment_at, created_at
    ))

    conn.commit()
    return cursor.lastrowid


def get_bookings_for_barber_date(barber: str, booking_date: str):
    return cursor.execute("""
    SELECT booking_time, duration_min
    FROM bookings
    WHERE barber = ? AND booking_date = ? AND status = 'active'
    ORDER BY booking_time
    """, (barber, booking_date)).fetchall()


def get_today_bookings(today_date: str):
    return cursor.execute("""
    SELECT *
    FROM bookings
    WHERE booking_date = ? AND status = 'active'
    ORDER BY booking_time
    """, (today_date,)).fetchall()


def get_recent_bookings(limit: int = 15):
    return cursor.execute("""
    SELECT *
    FROM bookings
    ORDER BY id DESC
    LIMIT ?
    """, (limit,)).fetchall()


def get_all_clients():
    return cursor.execute("""
    SELECT *
    FROM clients
    ORDER BY last_seen DESC
    """).fetchall()


def get_future_unreminded_bookings(now_iso: str):
    return cursor.execute("""
    SELECT *
    FROM bookings
    WHERE status = 'active' AND reminded = 0 AND appointment_at > ?
    ORDER BY appointment_at
    """, (now_iso,)).fetchall()


def mark_booking_reminded(booking_id: int):
    cursor.execute("UPDATE bookings SET reminded = 1 WHERE id = ?", (booking_id,))
    conn.commit()


def add_barber(
        name: str,
        experience: str,
        specialization: str,
        strong_sides: str,
        description: str,
        photo: str,
        workdays: str = "0,1,2,3,4,5,6",
        start_time: str = "10:00",
        end_time: str = "20:00"
):
    cursor.execute("""
    INSERT INTO barbers (name, experience, specialization, strong_sides, description, photo, workdays, start_time, end_time)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, experience, specialization, strong_sides, description, photo, workdays, start_time, end_time))
    conn.commit()


def get_barbers():
    return cursor.execute("SELECT * FROM barbers ORDER BY id").fetchall()


def get_barber(name: str):
    return cursor.execute("SELECT * FROM barbers WHERE name = ?", (name,)).fetchone()


def delete_barber(barber_id: int):
    cursor.execute("DELETE FROM barbers WHERE id = ?", (barber_id,))
    conn.commit()


def get_barber_names():
    rows = cursor.execute("SELECT name FROM barbers").fetchall()
    return [r["name"] for r in rows]


# ------------------------------------------------
# ФУНКЦИИ ДЛЯ ОТМЕНЫ ЗАПИСИ
# ------------------------------------------------

def get_active_bookings_for_user(user_id: int):
    """
    Все активные записи пользователя.
    ИСПРАВЛЕНО: убран фильтр по дате — показываем все active записи,
    чтобы пользователь мог отменить даже запись на сегодня/вчера.
    """
    return cursor.execute("""
    SELECT * FROM bookings
    WHERE user_id = ? AND status = 'active'
    ORDER BY booking_date DESC, booking_time DESC
    """, (user_id,)).fetchall()


def get_all_active_bookings(limit: int = 50):
    """
    Все активные записи для админа.
    ИСПРАВЛЕНО: убран фильтр по дате — показываем все active записи.
    """
    return cursor.execute("""
    SELECT * FROM bookings
    WHERE status = 'active'
    ORDER BY booking_date DESC, booking_time DESC
    LIMIT ?
    """, (limit,)).fetchall()


def get_booking_by_id(booking_id: int):
    return cursor.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()


def cancel_booking(booking_id: int):
    cursor.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
    conn.commit()


# ------------------------------------------------
# ИСТОРИЯ ЗАПИСЕЙ / АВТОАРХИВАЦИЯ
# ------------------------------------------------

def archive_expired_bookings():
    """
    Переводит все активные записи, время которых уже прошло,
    в статус 'completed' (история).
    Возвращает количество заархивированных записей.
    """
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
    result = cursor.execute("""
        UPDATE bookings
        SET status = 'completed'
        WHERE status = 'active'
          AND (booking_date || ' ' || booking_time) <= ?
    """, (now_iso,))
    conn.commit()
    return result.rowcount


def get_booking_history(limit: int = 50):
    """
    Все завершённые (completed) и отменённые (cancelled) записи —
    история за всё время, от новых к старым.
    """
    return cursor.execute("""
        SELECT *
        FROM bookings
        WHERE status IN ('completed', 'cancelled')
        ORDER BY appointment_at DESC
        LIMIT ?
    """, (limit,)).fetchall()