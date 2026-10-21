"""
Расчёт доступных слотов у одного конкретного мастера.

Рабочий график → кандидаты на начало услуги → отсеивание тех,
что пересекаются с блокировками времени и активными записями.
Всё, что "выше" одного мастера (агрегация по нескольким сразу),
живёт в availability.py.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.conf import settings
from django.utils import timezone

from ..models import Absence, Booking, Master, MasterService, Service, TimeBlock, WorkDay


DEFAULT_SLOT_STEP_MINUTES = 30


def get_slot_step() -> int:
    """
    Шаг сетки онлайн-записи в минутах (настройка BOOKING_SLOT_STEP_MINUTES).

    Сайт показывает клиенту время с этим шагом, и такой же шаг должен
    использоваться, когда запись создаётся: иначе с сайта можно было бы
    записаться на время, которого клиент не видел.
    """
    return int(
        getattr(settings, "BOOKING_SLOT_STEP_MINUTES", DEFAULT_SLOT_STEP_MINUTES),
    )


@dataclass
class AvailabilitySnapshot:
    """Предзагруженные данные для расчёта availability на диапазон дат.

    Снимок убирает N+1 в календарных endpoint'ах: после одного набора запросов
    каждый слот рассчитывается из памяти, без обращений к related managers.
    Это не резерв и не гарантия доступности при записи — create_booking всё
    равно повторно проверяет слот под блокировкой мастера.
    """

    master_services: dict[tuple[int, int], MasterService] = field(default_factory=dict)
    work_days: dict[tuple[int, date], WorkDay] = field(default_factory=dict)
    absent_dates: dict[int, set[date]] = field(default_factory=dict)
    time_blocks: dict[tuple[int, date], list[TimeBlock]] = field(default_factory=dict)
    bookings: dict[tuple[int, date], list[Booking]] = field(default_factory=dict)


def load_availability_snapshot(
    masters,
    date_from: date,
    date_to: date,
    *,
    service: Service | None = None,
) -> AvailabilitySnapshot:
    """Загружает нужные данные пачками для одного или нескольких мастеров."""
    master_list = list(masters)
    master_ids = [master.pk for master in master_list if master.pk is not None]
    snapshot = AvailabilitySnapshot()

    if not master_ids or date_to < date_from:
        return snapshot

    master_services = MasterService.objects.filter(
        master_id__in=master_ids,
        is_active=True,
    )
    if service is not None:
        master_services = master_services.filter(service_id=service.pk)
    snapshot.master_services = {
        (item.master_id, item.service_id): item
        for item in master_services
    }

    snapshot.work_days = {
        (item.master_id, item.date): item
        for item in WorkDay.objects.filter(
            master_id__in=master_ids,
            date__range=(date_from, date_to),
        )
    }

    absences = Absence.objects.filter(
        master_id__in=master_ids,
        start_date__lte=date_to,
        end_date__gte=date_from,
    )
    for absence in absences:
        if absence.master_id is None:
            continue
        master_id: int = absence.master_id
        first = max(date_from, absence.start_date)
        last = min(date_to, absence.end_date)
        current = first
        while current <= last:
            snapshot.absent_dates.setdefault(master_id, set()).add(current)
            current += timedelta(days=1)

    for block in TimeBlock.objects.filter(
        master_id__in=master_ids,
        date__range=(date_from, date_to),
    ):
        if block.master_id is None:
            continue
        snapshot.time_blocks.setdefault((int(block.master_id), block.date), []).append(block)

    for booking in Booking.objects.filter(
        master_id__in=master_ids,
        date__range=(date_from, date_to),
        status__in=Booking.ACTIVE_STATUSES,
    ):
        if booking.master_id is None:
            continue
        snapshot.bookings.setdefault((int(booking.master_id), booking.date), []).append(booking)

    return snapshot


def get_working_intervals(
    master: Master,
    target_date: date,
    *,
    snapshot: AvailabilitySnapshot | None = None,
):
    """
    Возвращает рабочие интервалы мастера на конкретную дату.

    Например:
    [
        (09:00, 13:00),
        (14:00, 18:00),
    ]

    Источник данных — рабочие дни мастера (WorkDay). Если на эту дату
    рабочего дня нет, мастер не отмечен и интервалов нет. Отсутствие
    (отпуск, больничный, отгул) сильнее рабочего дня: пока оно
    действует, интервалов нет, даже если рабочий день отмечен.
    """

    if snapshot is not None:
        if target_date in snapshot.absent_dates.get(master.pk, set()):
            return []
        work_day = snapshot.work_days.get((master.pk, target_date))
    else:
        is_absent = master.absences.filter(
            start_date__lte=target_date,
            end_date__gte=target_date,
        ).exists()

        if is_absent:
            return []

        work_day = master.work_days.filter(date=target_date).first()

    if work_day is None:
        return []

    return work_day.get_intervals()


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

    if duration_minutes <= 0:
        raise ValueError("duration_minutes должен быть больше нуля.")
    if slot_step_minutes <= 0:
        raise ValueError("slot_step_minutes должен быть больше нуля.")

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


def get_active_bookings(
    master: Master,
    target_date: date,
):
    """
    Возвращает активные записи мастера на конкретную дату.

    Какие статусы блокируют время, задано в Booking.ACTIVE_STATUSES
    (сейчас NEW и CONFIRMED); остальные записи время не занимают.
    """
    return Booking.objects.filter(
        master=master,
        date=target_date,
        status__in=Booking.ACTIVE_STATUSES,
    )


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


def get_available_slots(
    master: Master,
    service: Service,
    target_date: date,
    slot_step_minutes: int = 15,
    now=None,
    *,
    snapshot: AvailabilitySnapshot | None = None,
):
    """
    Возвращает список доступных начал услуги у конкретного мастера
    на конкретную дату, с учётом рабочего графика, исключений,
    блокировок времени, уже существующих активных записей и
    минимального отступа BOOKING_MIN_LEAD_MINUTES перед началом
    услуги (если target_date — сегодня).

    Если мастер не оказывает данную услугу (нет активной записи
    в MasterService), возвращает пустой список.

    Параметр now нужен только для тестов, чтобы не зависеть от
    реального времени на часах, — в проде вызывающий код его не
    передаёт, и берётся timezone.localtime().
    """

    if slot_step_minutes <= 0:
        raise ValueError("slot_step_minutes должен быть больше нуля.")

    if snapshot is not None:
        master_service = snapshot.master_services.get((master.pk, service.pk))
    else:
        try:
            master_service = master.master_services.get(
                service=service,
                is_active=True,
            )
        except MasterService.DoesNotExist:
            return []

    if master_service is None:
        return []

    duration_minutes = master_service.duration
    if duration_minutes <= 0:
        return []

    working_intervals = get_working_intervals(
        master,
        target_date,
        snapshot=snapshot,
    )

    if not working_intervals:
        return []

    candidates = get_candidate_starts(
        working_intervals,
        duration_minutes,
        slot_step_minutes,
    )

    if snapshot is not None:
        time_blocks = snapshot.time_blocks.get((master.pk, target_date), [])
    else:
        time_blocks = master.time_blocks.filter(date=target_date)

    candidates = filter_candidates_by_time_blocks(
        candidates,
        duration_minutes,
        time_blocks,
    )

    if snapshot is not None:
        bookings = snapshot.bookings.get((master.pk, target_date), [])
    else:
        bookings = get_active_bookings(master, target_date)

    candidates = filter_candidates_by_bookings(
        candidates,
        bookings,
        duration_minutes,
    )

    current_moment = now or timezone.localtime()

    if target_date == current_moment.date():
        cutoff_moment = current_moment + timedelta(
            minutes=settings.BOOKING_MIN_LEAD_MINUTES,
        )

        if cutoff_moment.date() != target_date:
            # Отступ перевалил за полночь — на сегодня всё, что
            # оставалось, уже попадает в "меньше часа до начала".
            return []

        cutoff_time = cutoff_moment.time()
        candidates = [
            candidate
            for candidate in candidates
            if candidate >= cutoff_time
        ]

    return candidates
