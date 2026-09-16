from datetime import date, datetime, time, timedelta

from .models import Master, Service

def get_working_intervals(
    master: Master,
    target_date: date,
):
    """
    Возвращает рабочие интервалы мастера на конкретную дату.

    Например:
    [
        (09:00, 13:00),
        (14:00, 18:00),
    ]

    Если мастер в этот день не работает или день закрыт,
    возвращает пустой список.
    """

    exception = master.schedule_exceptions.filter(
        date=target_date,
    ).first()

    if exception is not None:
        if exception.is_closed:
            return []

        return [
            (exception.start_time, exception.end_time),
        ]

    weekday = target_date.weekday()

    working_hours = master.working_hours.filter(
        weekday=weekday,
    ).order_by("start_time")

    return [
        (working_hour.start_time, working_hour.end_time)
        for working_hour in working_hours
    ]

def get_candidate_starts(
    working_intervals,
    duration_minutes: int,
    slot_step_minutes: int = 15,
):
    """
    Возвращает возможные начала услуги внутри рабочих интервалов.

    Кандидаты создаются с заданным шагом и должны полностью
    помещать услугу заданной продолжительности в рабочий интервал.
    """

    candidates = []
    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=slot_step_minutes)

    for start_time, end_time in working_intervals:
        current = datetime.combine(date.min, start_time)
        interval_end = datetime.combine(date.min, end_time)

        while current + duration <= interval_end:
            candidates.append(current.time())
            current += step

    return candidates

def intervals_overlap(
    start_a,
    end_a,
    start_b,
    end_b,
):
    """
    Проверяет, пересекаются ли два временных интервала.

    Интервалы, которые просто соприкасаются границами,
    пересечением не считаются.

    Например:
    14:00–14:30 и 14:30–15:00 → не пересекаются.
    """

    return start_a < end_b and end_a > start_b


def filter_candidates_by_time_blocks(
    candidates,
    duration_minutes: int,
    time_blocks,
):
    """
    Убирает кандидатов, которые пересекаются с блокировками времени.

    Кандидат считается недоступным, если вся услуга
    пересекается хотя бы с одной блокировкой.
    """

    available_candidates = []
    duration = timedelta(minutes=duration_minutes)

    for candidate in candidates:
        candidate_start = candidate
        candidate_end = (
            datetime.combine(date.min, candidate_start) + duration
        ).time()

        has_overlap = any(
            intervals_overlap(
                candidate_start,
                candidate_end,
                block.start_time,
                block.end_time,
            )
            for block in time_blocks
        )

        if not has_overlap:
            available_candidates.append(candidate)

    return available_candidates

def filter_candidates_by_bookings(
    candidates,
    bookings,
    service_duration_minutes: int,
):
    """
    Убирает кандидатов, которые пересекаются
    с активными записями клиентов.

    NEW и CONFIRMED должны передаваться в bookings.
    CANCELLED сюда не передаём, поэтому отменённые записи
    не блокируют время.
    """

    available_candidates = []
    service_duration = timedelta(minutes=service_duration_minutes)

    for candidate in candidates:
        candidate_start = candidate
        candidate_end = (
            datetime.combine(date.min, candidate_start)
            + service_duration
        ).time()

        has_overlap = False

        for booking in bookings:
            booking_start = booking.start_time
            booking_end = (
                datetime.combine(date.min, booking_start)
                + timedelta(minutes=booking.duration)
            ).time()

            if intervals_overlap(
                candidate_start,
                candidate_end,
                booking_start,
                booking_end,
            ):
                has_overlap = True
                break

        if not has_overlap:
            available_candidates.append(candidate)

    return available_candidates
