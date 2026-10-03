"""
Перенос старого расписания в новые рабочие дни (ВРЕМЕННЫЙ модуль).

Старая схема: «обычная неделя» (WorkingHours) плюс исключения на отдельные
даты (ScheduleException). Новая схема: по одной записи WorkDay на каждую
рабочую дату. Этот модуль один раз разворачивает старое расписание
в рабочие дни на заданный период и после этого будет удалён вместе
со старыми моделями.

Правила переноса для каждой даты мастера:

- рабочий день на эту дату уже есть  -> не трогаем (команду можно
  безопасно запускать повторно);
- есть закрытое исключение            -> рабочий день НЕ создаётся;
- есть исключение с особыми часами    -> рабочий день с этими часами
  (даже если по обычной неделе мастер в этот день не работал);
- иначе берётся обычная неделя        -> рабочий день, если по ней мастер
  в этот день недели работает; перерыв берётся из «дыры» между
  двумя интервалами.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import Iterable, Optional

from django.db import transaction

from ..models import Master, ScheduleException, WorkDay, WorkingHours
from .weekly_schedule import intervals_to_day


@dataclass
class ConversionReport:
    """Итог переноса: сколько чего создано и о чём стоит знать."""

    created: int = 0
    skipped_existing: int = 0
    closed_days: int = 0
    warnings: list[str] = field(default_factory=list)
    closed_with_reason: list[str] = field(default_factory=list)

    def merge(self, other: "ConversionReport") -> None:
        self.created += other.created
        self.skipped_existing += other.skipped_existing
        self.closed_days += other.closed_days
        self.warnings.extend(other.warnings)
        self.closed_with_reason.extend(other.closed_with_reason)


def convert_master_schedule(
    master: Master,
    date_from: date,
    date_to: date,
    dry_run: bool = False,
) -> ConversionReport:
    """Переносит расписание одного мастера на период [date_from, date_to]."""
    report = ConversionReport()

    # Обычная неделя: день недели -> список интервалов.
    weekly: dict[int, list[tuple[time, time]]] = defaultdict(list)
    for row in WorkingHours.objects.filter(master=master):
        weekly[row.weekday].append((row.start_time, row.end_time))

    for weekday, intervals in weekly.items():
        if len(intervals) > 2:
            report.warnings.append(
                f"{master.name}: в день «{WorkingHours.Weekday(weekday).label}» "
                "больше двух интервалов — перенесён только первый перерыв."
            )

    exceptions = {
        exception.date: exception
        for exception in ScheduleException.objects.filter(
            master=master,
            date__range=(date_from, date_to),
        )
    }
    existing_dates = set(
        WorkDay.objects.filter(
            master=master,
            date__range=(date_from, date_to),
        ).values_list("date", flat=True)
    )

    new_days: list[WorkDay] = []
    current = date_from

    while current <= date_to:
        if current in existing_dates:
            report.skipped_existing += 1

        elif current in exceptions:
            exception = exceptions[current]

            if exception.is_closed:
                report.closed_days += 1
                if exception.reason:
                    report.closed_with_reason.append(
                        f"{master.name}, {current:%d.%m.%Y}: {exception.reason}"
                    )

            elif exception.start_time is not None and exception.end_time is not None:
                new_days.append(
                    WorkDay(
                        master=master,
                        date=current,
                        start_time=exception.start_time,
                        end_time=exception.end_time,
                    )
                )

        else:
            day = intervals_to_day(weekly.get(current.weekday(), []))

            if day.works and day.start is not None and day.end is not None:
                new_days.append(
                    WorkDay(
                        master=master,
                        date=current,
                        start_time=day.start,
                        end_time=day.end,
                        break_start=day.break_start,
                        break_end=day.break_end,
                    )
                )

        current += timedelta(days=1)

    report.created = len(new_days)

    if not dry_run and new_days:
        with transaction.atomic():
            WorkDay.objects.bulk_create(new_days)

    return report


def convert_old_schedule(
    date_from: date,
    date_to: date,
    dry_run: bool = False,
    masters: Optional[Iterable[Master]] = None,
) -> ConversionReport:
    """Переносит расписание всех мастеров (или переданных) на период."""
    if masters is None:
        masters = Master.objects.all()

    total = ConversionReport()

    for master in masters:
        total.merge(
            convert_master_schedule(master, date_from, date_to, dry_run),
        )

    return total
