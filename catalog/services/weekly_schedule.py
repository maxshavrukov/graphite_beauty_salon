"""
Недельный график мастера в «человеческом» виде.

В базе график хранится как набор интервалов WorkingHours: на каждый день
недели одна или несколько записей. Для админа удобнее другая картинка:
на каждый день — «работает / выходной», время начала и конца и
необязательный перерыв. Этот модуль переводит из одного вида в другой.

Перерыв хранится как «дырка» между двумя интервалами:

    09:00–18:00 с перерывом 13:00–14:00  <->  09:00–13:00 и 14:00–18:00

Поэтому расчёт свободных слотов (scheduling.py) менять не нужно: он и так
умеет работать с несколькими интервалами за день.

Ограничение: «день с перерывом» умеет описать не больше одного перерыва.
Если у дня в базе больше двух интервалов (такое можно создать только
напрямую), при показе будет виден только первый перерыв, а при сохранении
именно этого дня остальные интервалы заменятся.
"""

from dataclasses import dataclass
from datetime import time
from typing import Iterable, Optional

from django.db import transaction

from catalog.models import Master, WorkingHours

Interval = tuple[time, time]


@dataclass(frozen=True)
class DaySchedule:
    """Один день недели: работает ли мастер, когда и есть ли перерыв."""

    works: bool
    start: Optional[time] = None
    end: Optional[time] = None
    break_start: Optional[time] = None
    break_end: Optional[time] = None


def get_day_error(day: DaySchedule) -> Optional[str]:
    """
    Проверяет заполнение дня. Возвращает текст ошибки для человека
    или None, если всё в порядке.
    """
    if not day.works:
        return None

    if day.start is None or day.end is None:
        return "Укажите время начала и конца работы."

    if day.start >= day.end:
        return "Конец работы должен быть позже начала."

    if (day.break_start is None) != (day.break_end is None):
        return (
            "Для перерыва укажите и начало, и конец "
            "(или оставьте оба поля пустыми)."
        )

    if day.break_start is not None and day.break_end is not None:
        if day.break_start >= day.break_end:
            return "Конец перерыва должен быть позже его начала."

        if day.break_start <= day.start or day.break_end >= day.end:
            return "Перерыв должен быть внутри рабочего времени."

    return None


def day_to_intervals(day: DaySchedule) -> list[Interval]:
    """
    Превращает день в список рабочих интервалов.

    Выходной -> [], день без перерыва -> один интервал,
    день с перерывом -> два интервала.
    Если день заполнен неверно — ValueError с понятным текстом.
    """
    error = get_day_error(day)
    if error is not None:
        raise ValueError(error)

    if not day.works or day.start is None or day.end is None:
        return []

    if day.break_start is None or day.break_end is None:
        return [(day.start, day.end)]

    return [
        (day.start, day.break_start),
        (day.break_end, day.end),
    ]


def intervals_to_day(intervals: Iterable[Interval]) -> DaySchedule:
    """
    Обратное преобразование: интервалы из базы -> день для формы.

    Перерывом считается первый «просвет» между интервалами. Интервалы,
    которые касаются друг друга (09–13 и 13–18), считаются одним
    непрерывным рабочим временем, без перерыва.
    """
    ordered = sorted(intervals)

    if not ordered:
        return DaySchedule(works=False)

    start = ordered[0][0]
    end = max(interval_end for _, interval_end in ordered)

    break_start: Optional[time] = None
    break_end: Optional[time] = None

    for (_, previous_end), (next_start, _) in zip(ordered, ordered[1:]):
        if previous_end < next_start:
            break_start, break_end = previous_end, next_start
            break

    return DaySchedule(
        works=True,
        start=start,
        end=end,
        break_start=break_start,
        break_end=break_end,
    )


def get_weekly_schedule(master: Master) -> dict[int, DaySchedule]:
    """
    Недельный график мастера: ключ — номер дня недели (0 = понедельник),
    значение — DaySchedule. В словаре всегда все семь дней.
    """
    by_weekday: dict[int, list[Interval]] = {
        weekday: [] for weekday in WorkingHours.Weekday.values
    }

    # Мастер ещё не сохранён (например, его создают в админке):
    # в базе искать нечего, а фильтр по несохранённому объекту — ошибка.
    if master.pk is not None:
        for row in WorkingHours.objects.filter(master=master):
            by_weekday[row.weekday].append((row.start_time, row.end_time))

    return {
        weekday: intervals_to_day(intervals)
        for weekday, intervals in by_weekday.items()
    }


def save_weekly_schedule(
    master: Master,
    week: dict[int, DaySchedule],
) -> None:
    """
    Сохраняет график: для каждого дня из `week` старые интервалы мастера
    заменяются новыми. Дни, которых в `week` нет, не затрагиваются.

    Сначала проверяется и пересчитывается весь `week`, и только потом
    база меняется — поэтому при ошибке в одном дне не сохранится ничего.
    """
    valid_weekdays = set(WorkingHours.Weekday.values)

    for weekday in week:
        if weekday not in valid_weekdays:
            raise ValueError(f"Неизвестный день недели: {weekday}")

    new_intervals = {
        weekday: day_to_intervals(day) for weekday, day in week.items()
    }

    with transaction.atomic():
        for weekday, intervals in new_intervals.items():
            WorkingHours.objects.filter(
                master=master,
                weekday=weekday,
            ).delete()

            WorkingHours.objects.bulk_create(
                [
                    WorkingHours(
                        master=master,
                        weekday=weekday,
                        start_time=start,
                        end_time=end,
                    )
                    for start, end in intervals
                ]
            )
