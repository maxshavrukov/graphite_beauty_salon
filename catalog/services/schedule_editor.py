"""
Редактор расписания мастера: всё, что админ делает с рабочими днями
и отсутствиями, и всё, что нужно показать ему о расписании.

Модуль не знает ни про страницы, ни про формы: он принимает обычные
даты и значения, меняет базу и возвращает понятные итоги. Поэтому им
пользуются и страница-календарь в админке, и любой будущий экран.

Правила расписания:

- мастер работает только в дни, у которых есть запись WorkDay;
- отсутствие (отпуск, больничный, отгул) сильнее рабочего дня, но не
  стирает его: отменили отсутствие — рабочие дни снова действуют;
- записи клиентов этот модуль сам никогда не отменяет и не переносит:
  он только умеет найти их (find_active_bookings), а решение принимает
  человек.

Неверные данные от пользователя (время, даты отсутствия) приводят к
ValidationError с понятным текстом, ошибки вызова (например, пустой
список дат) — к ValueError.
"""

import calendar
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Iterable, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from ..models import Absence, Booking, Master, WorkDay

# Записи, которые занимают время мастера (отменённые и завершённые — нет).
ACTIVE_BOOKING_STATUSES = (Booking.Status.NEW, Booking.Status.CONFIRMED)

# За сколько дней до конца расписания предупреждать админа.
DEFAULT_WARNING_DAYS = 21

STATE_EMPTY = "empty"      # мастер в этот день не отмечен
STATE_WORKING = "working"  # рабочий день
STATE_ABSENT = "absent"    # отпуск, больничный или отгул


# ---------------------------------------------------------------------------
# Итоги операций
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkDayChange:
    """Итог set_work_days: сколько дней создано, изменено и не потребовало правки."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclass(frozen=True)
class CopyResult:
    """Итог копирования рабочих дней."""

    created: int = 0
    replaced: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class ScheduleStatus:
    """До какой даты заполнено расписание и пора ли его продлевать."""

    filled_until: Optional[date]
    days_left: int
    is_low: bool


@dataclass(frozen=True)
class CalendarDay:
    """Один день календаря мастера со всем, что нужно показать."""

    day: date
    work_day: Optional[WorkDay]
    absence: Optional[Absence]
    bookings_count: int
    is_today: bool
    is_past: bool

    @property
    def state(self) -> str:
        # Отсутствие сильнее рабочего дня, но work_day остаётся доступным.
        if self.absence is not None:
            return STATE_ABSENT

        if self.work_day is not None:
            return STATE_WORKING

        return STATE_EMPTY


# ---------------------------------------------------------------------------
# Рабочие дни
# ---------------------------------------------------------------------------


def _check_day_times(
    start_time: Optional[time],
    end_time: Optional[time],
    break_start: Optional[time],
    break_end: Optional[time],
) -> None:
    """Проверяет время дня теми же правилами, что и сама модель WorkDay."""
    if start_time is None or end_time is None:
        raise ValidationError("Укажите время начала и конца работы.")

    WorkDay(
        start_time=start_time,
        end_time=end_time,
        break_start=break_start,
        break_end=break_end,
    ).clean()


def set_work_days(
    master: Master,
    dates: Iterable[date],
    start_time: Optional[time],
    end_time: Optional[time],
    break_start: Optional[time] = None,
    break_end: Optional[time] = None,
) -> WorkDayChange:
    """
    Отмечает выбранные даты рабочими: новые дни создаёт, у уже отмеченных
    меняет время. Всё или ничего: при неверном времени не сохранится ни
    один день.
    """
    unique_dates = sorted(set(dates))

    if not unique_dates:
        raise ValueError("Не выбрано ни одной даты.")

    _check_day_times(start_time, end_time, break_start, break_end)

    with transaction.atomic():
        existing = {
            work_day.date: work_day
            for work_day in WorkDay.objects.filter(
                master=master,
                date__in=unique_dates,
            )
        }

        to_create: list[WorkDay] = []
        to_update: list[WorkDay] = []
        unchanged = 0

        for day in unique_dates:
            current = existing.get(day)

            if current is None:
                to_create.append(
                    WorkDay(
                        master=master,
                        date=day,
                        start_time=start_time,
                        end_time=end_time,
                        break_start=break_start,
                        break_end=break_end,
                    )
                )
                continue

            same = (
                current.start_time == start_time
                and current.end_time == end_time
                and current.break_start == break_start
                and current.break_end == break_end
            )

            if same:
                unchanged += 1
                continue

            current.start_time = start_time
            current.end_time = end_time
            current.break_start = break_start
            current.break_end = break_end
            to_update.append(current)

        WorkDay.objects.bulk_create(to_create)

        if to_update:
            WorkDay.objects.bulk_update(
                to_update,
                ["start_time", "end_time", "break_start", "break_end"],
            )

    return WorkDayChange(
        created=len(to_create),
        updated=len(to_update),
        unchanged=unchanged,
    )


def remove_work_days(master: Master, dates: Iterable[date]) -> int:
    """Снимает рабочие дни на выбранные даты. Возвращает, сколько снято."""
    unique_dates = set(dates)

    if not unique_dates:
        return 0

    deleted, _ = WorkDay.objects.filter(
        master=master,
        date__in=unique_dates,
    ).delete()

    return deleted


# ---------------------------------------------------------------------------
# Отсутствия
# ---------------------------------------------------------------------------


def create_absence(
    master: Master,
    kind: str,
    start_date: date,
    end_date: date,
    comment: str = "",
) -> Absence:
    """
    Оформляет отсутствие мастера на диапазон дат (включительно).
    Рабочие дни в этот период не удаляются. Пересечение с другим
    отсутствием того же мастера — ValidationError.
    """
    absence = Absence(
        master=master,
        kind=kind,
        start_date=start_date,
        end_date=end_date,
        comment=comment,
    )
    absence.full_clean()
    absence.save()

    return absence


# ---------------------------------------------------------------------------
# Конфликты с записями клиентов
# ---------------------------------------------------------------------------


def find_active_bookings(master: Master, dates: Iterable[date]) -> list[Booking]:
    """Активные записи мастера на выбранные даты (по порядку времени)."""
    unique_dates = set(dates)

    if not unique_dates:
        return []

    return list(
        Booking.objects.filter(
            master=master,
            date__in=unique_dates,
            status__in=ACTIVE_BOOKING_STATUSES,
        ).order_by("date", "start_time")
    )


def find_active_bookings_in_range(
    master: Master,
    start_date: date,
    end_date: date,
) -> list[Booking]:
    """Активные записи мастера в диапазоне дат, границы включены."""
    return list(
        Booking.objects.filter(
            master=master,
            date__range=(start_date, end_date),
            status__in=ACTIVE_BOOKING_STATUSES,
        ).order_by("date", "start_time")
    )


# ---------------------------------------------------------------------------
# «Расписание заполнено до …»
# ---------------------------------------------------------------------------


def get_filled_until(master: Master) -> Optional[date]:
    """Последняя дата, на которую у мастера отмечен рабочий день."""
    return (
        WorkDay.objects.filter(master=master)
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )


def get_schedule_status(
    master: Master,
    today: Optional[date] = None,
    warning_days: Optional[int] = None,
) -> ScheduleStatus:
    """
    Сколько дней вперёд заполнено расписание и не пора ли его продлевать.

    Порог берётся из параметра, затем из настройки SCHEDULE_WARNING_DAYS,
    затем равен 21 дню. Ровно на пороге предупреждения ещё нет.
    """
    if today is None:
        today = timezone.localdate()

    if warning_days is None:
        warning_days = getattr(settings, "SCHEDULE_WARNING_DAYS", DEFAULT_WARNING_DAYS)

    filled_until = get_filled_until(master)

    if filled_until is None:
        return ScheduleStatus(filled_until=None, days_left=0, is_low=True)

    days_left = max(0, (filled_until - today).days)

    return ScheduleStatus(
        filled_until=filled_until,
        days_left=days_left,
        is_low=days_left < warning_days,
    )


# ---------------------------------------------------------------------------
# Копирование и продление
# ---------------------------------------------------------------------------


def copy_work_days(
    master: Master,
    source_start: date,
    source_end: date,
    shift_weeks: int,
    overwrite: bool = False,
) -> CopyResult:
    """
    Копирует рабочие дни из периода [source_start, source_end] вперёд (или
    назад) на целое число недель, поэтому дни недели совпадают.

    Уже заполненные даты по умолчанию не трогаются (считаются пропущенными);
    с overwrite=True их время заменяется. Отсутствия не копируются: они
    разовые.
    """
    if source_end < source_start:
        raise ValueError("Конец периода не может быть раньше начала.")

    if shift_weeks == 0:
        raise ValueError("Сдвиг должен быть не нулевым.")

    shift = timedelta(days=7 * shift_weeks)

    sources = list(
        WorkDay.objects.filter(
            master=master,
            date__range=(source_start, source_end),
        )
    )

    with transaction.atomic():
        existing = {
            work_day.date: work_day
            for work_day in WorkDay.objects.filter(
                master=master,
                date__in=[source.date + shift for source in sources],
            )
        }

        to_create: list[WorkDay] = []
        to_update: list[WorkDay] = []
        skipped = 0

        for source in sources:
            target_date = source.date + shift
            current = existing.get(target_date)

            if current is None:
                to_create.append(
                    WorkDay(
                        master=master,
                        date=target_date,
                        start_time=source.start_time,
                        end_time=source.end_time,
                        break_start=source.break_start,
                        break_end=source.break_end,
                    )
                )
            elif overwrite:
                current.start_time = source.start_time
                current.end_time = source.end_time
                current.break_start = source.break_start
                current.break_end = source.break_end
                to_update.append(current)
            else:
                skipped += 1

        WorkDay.objects.bulk_create(to_create)

        if to_update:
            WorkDay.objects.bulk_update(
                to_update,
                ["start_time", "end_time", "break_start", "break_end"],
            )

    return CopyResult(
        created=len(to_create),
        replaced=len(to_update),
        skipped=skipped,
    )


def extend_schedule(
    master: Master,
    weeks: int = 4,
    overwrite: bool = False,
) -> CopyResult:
    """
    Продлевает расписание: последние `weeks` недель расписания повторяются
    сразу за его концом. Можно вызывать снова — продление пойдёт дальше.
    """
    if weeks < 1:
        raise ValueError("Число недель должно быть не меньше 1.")

    last_day = get_filled_until(master)

    if last_day is None:
        raise ValidationError(
            "У мастера нет расписания, которое можно продлить."
        )

    return copy_work_days(
        master,
        source_start=last_day - timedelta(days=7 * weeks - 1),
        source_end=last_day,
        shift_weeks=weeks,
        overwrite=overwrite,
    )


# ---------------------------------------------------------------------------
# Данные для календаря
# ---------------------------------------------------------------------------


def get_month_calendar(
    master: Master,
    year: int,
    month: int,
    today: Optional[date] = None,
) -> list[CalendarDay]:
    """
    Все дни месяца мастера: рабочий день, отсутствие и число активных
    записей. Три запроса к базе на весь месяц.
    """
    if today is None:
        today = timezone.localdate()

    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    work_days = {
        work_day.date: work_day
        for work_day in WorkDay.objects.filter(
            master=master,
            date__range=(first_day, last_day),
        )
    }

    absences = list(
        Absence.objects.filter(
            master=master,
            start_date__lte=last_day,
            end_date__gte=first_day,
        )
    )

    bookings_by_date = {
        row["date"]: row["total"]
        for row in Booking.objects.filter(
            master=master,
            date__range=(first_day, last_day),
            status__in=ACTIVE_BOOKING_STATUSES,
        )
        .values("date")
        .annotate(total=Count("id"))
    }

    days: list[CalendarDay] = []
    current = first_day

    while current <= last_day:
        absence = next(
            (
                item
                for item in absences
                if item.start_date <= current <= item.end_date
            ),
            None,
        )

        days.append(
            CalendarDay(
                day=current,
                work_day=work_days.get(current),
                absence=absence,
                bookings_count=bookings_by_date.get(current, 0),
                is_today=current == today,
                is_past=current < today,
            )
        )
        current += timedelta(days=1)

    return days
