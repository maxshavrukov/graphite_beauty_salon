"""
Бизнес-логика каталога, разбитая по смыслу на три файла:

- scheduling.py   — расчёт доступных слотов у одного мастера
- availability.py — агрегация доступности по всем мастерам услуги
- booking.py       — создание записи с защитой от гонки

Всё реэкспортируется отсюда, поэтому снаружи (в тестах, вьюхах)
ничего менять не нужно — `from catalog.services import X` работает
так же, как раньше, когда всё было в одном services.py.
"""

from .availability import (
    get_available_dates_for_master,
    get_available_dates_for_service,
    get_available_masters_for_slot,
    get_available_times_for_service,
    get_masters_for_service,
)
from .booking import (
    SlotUnavailableError,
    create_booking,
    get_booking_end_time,
    validate_booking_slot,
)
from .scheduling import (
    filter_candidates_by_bookings,
    filter_candidates_by_time_blocks,
    get_active_bookings,
    get_available_slots,
    get_candidate_starts,
    get_working_intervals,
    intervals_overlap,
)

__all__ = [
    "SlotUnavailableError",
    "create_booking",
    "filter_candidates_by_bookings",
    "filter_candidates_by_time_blocks",
    "get_active_bookings",
    "get_available_dates_for_master",
    "get_available_dates_for_service",
    "get_available_masters_for_slot",
    "get_available_slots",
    "get_available_times_for_service",
    "get_booking_end_time",
    "get_candidate_starts",
    "get_masters_for_service",
    "get_working_intervals",
    "intervals_overlap",
    "validate_booking_slot",
]
