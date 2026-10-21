"""
Бизнес-логика каталога, разбитая по смыслу на пять файлов:

- scheduling.py      — расчёт доступных слотов у одного мастера
- availability.py    — агрегация доступности по всем мастерам услуги
- booking.py         — создание записи с защитой от гонки
- booking_changes.py — смена статуса и перенос существующей записи
- schedule_editor.py — редактор расписания: рабочие дни, отсутствия,
                       «заполнено до», копирование и продление

Всё реэкспортируется отсюда, поэтому снаружи (в тестах, вьюхах)
ничего менять не нужно — `from catalog.services import X` работает
так же, как раньше, когда всё было в одном services.py.
"""

from .scheduling import get_slot_step
from .availability import (
    get_available_dates_for_master,
    get_available_dates_for_service,
    get_available_masters_for_slot,
    get_available_times_for_service,
    get_masters_for_service,
)
from .booking_changes import (
    BookingStateError,
    can_change_status,
    change_booking_status,
    reschedule_booking,
    validate_reschedule,
)
from .booking import (
    SlotUnavailableError,
    create_booking,
    get_booking_end_time,
    validate_booking_slot,
)
from .schedule_editor import (
    CalendarDay,
    CopyResult,
    ScheduleStatus,
    WorkDayChange,
    copy_work_days,
    create_absence,
    extend_schedule,
    find_active_bookings,
    find_active_bookings_in_range,
    get_filled_until,
    get_month_calendar,
    get_schedule_status,
    remove_work_days,
    set_work_days,
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
    "BookingStateError",
    "CalendarDay",
    "CopyResult",
    "ScheduleStatus",
    "SlotUnavailableError",
    "WorkDayChange",
    "can_change_status",
    "change_booking_status",
    "copy_work_days",
    "create_absence",
    "create_booking",
    "extend_schedule",
    "filter_candidates_by_bookings",
    "filter_candidates_by_time_blocks",
    "find_active_bookings",
    "find_active_bookings_in_range",
    "get_active_bookings",
    "get_available_dates_for_master",
    "get_available_dates_for_service",
    "get_available_masters_for_slot",
    "get_available_slots",
    "get_available_times_for_service",
    "get_booking_end_time",
    "get_candidate_starts",
    "get_filled_until",
    "get_masters_for_service",
    "get_slot_step",
    "get_month_calendar",
    "get_schedule_status",
    "get_working_intervals",
    "intervals_overlap",
    "remove_work_days",
    "reschedule_booking",
    "set_work_days",
    "validate_booking_slot",
    "validate_reschedule",
]
