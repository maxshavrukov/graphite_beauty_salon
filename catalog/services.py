from datetime import date, datetime, time, timedelta

from django.db import transaction

from .models import Booking, Master, MasterService, Service

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

def get_active_bookings(
    master: Master,
    target_date: date,
):
    """
    Возвращает активные записи мастера на конкретную дату.

    NEW и CONFIRMED блокируют время.
    CANCELLED и COMPLETED не блокируют.
    """
    return Booking.objects.filter(
        master=master,
        date=target_date,
        status__in=[
            Booking.Status.NEW,
            Booking.Status.CONFIRMED,
        ],
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
):
    """
    Возвращает список доступных начал услуги у конкретного мастера
    на конкретную дату, с учётом рабочего графика, исключений,
    блокировок времени и уже существующих активных записей.

    Если мастер не оказывает данную услугу (нет активной записи
    в MasterService), возвращает пустой список.
    """

    try:
        master_service = master.master_services.get(
            service=service,
            is_active=True,
        )
    except MasterService.DoesNotExist:
        return []

    duration_minutes = master_service.duration

    working_intervals = get_working_intervals(master, target_date)

    if not working_intervals:
        return []

    candidates = get_candidate_starts(
        working_intervals,
        duration_minutes,
        slot_step_minutes,
    )

    time_blocks = master.time_blocks.filter(date=target_date)

    candidates = filter_candidates_by_time_blocks(
        candidates,
        duration_minutes,
        time_blocks,
    )

    bookings = get_active_bookings(master, target_date)

    candidates = filter_candidates_by_bookings(
        candidates,
        bookings,
        duration_minutes,
    )

    return candidates


def get_masters_for_service(service: Service):
    """
    Возвращает активных мастеров, оказывающих данную услугу
    (есть активная запись в MasterService).
    """

    return Master.objects.filter(
        master_services__service=service,
        master_services__is_active=True,
        is_active=True,
    ).distinct()


def get_available_dates_for_service(
    service: Service,
    date_from: date,
    date_to: date,
    slot_step_minutes: int = 15,
):
    """
    Возвращает список дат в диапазоне [date_from, date_to] (включительно),
    на которые есть хотя бы один свободный слот хотя бы у одного мастера,
    оказывающего услугу.

    Ограничение диапазона дат вперёд (например, 14 дней) — забота
    вызывающего кода (view/настройки), а не этой функции.
    """

    masters = list(get_masters_for_service(service))

    if not masters:
        return []

    available_dates = []
    current = date_from

    while current <= date_to:
        has_slot = any(
            get_available_slots(
                master,
                service,
                current,
                slot_step_minutes,
            )
            for master in masters
        )

        if has_slot:
            available_dates.append(current)

        current += timedelta(days=1)

    return available_dates


def get_available_times_for_service(
    service: Service,
    target_date: date,
    slot_step_minutes: int = 15,
):
    """
    Возвращает объединённый список времени, доступного у любого
    из мастеров, оказывающих услугу, на указанную дату.

    Результат — отсортированный список без повторов. То, что время
    входит в результат, не означает, что оно свободно у всех
    мастеров сразу — конкретных мастеров на это время нужно
    смотреть через get_available_masters_for_slot.
    """

    masters = get_masters_for_service(service)

    available_times = set()

    for master in masters:
        slots = get_available_slots(
            master,
            service,
            target_date,
            slot_step_minutes,
        )
        available_times.update(slots)

    return sorted(available_times)


def get_available_masters_for_slot(
    service: Service,
    target_date: date,
    start_time: time,
    slot_step_minutes: int = 15,
):
    """
    Возвращает мастеров, оказывающих услугу и свободных именно
    в указанное время на указанную дату, вместе с ценой услуги
    у каждого мастера.

    Возвращает список словарей вида:
    [{"master": <Master>, "price": Decimal("450.00")}, ...]
    """

    master_services = MasterService.objects.filter(
        service=service,
        is_active=True,
        master__is_active=True,
    ).select_related("master")

    available = []

    for master_service in master_services:
        slots = get_available_slots(
            master_service.master,
            service,
            target_date,
            slot_step_minutes,
        )

        if start_time in slots:
            available.append({
                "master": master_service.master,
                "price": master_service.price,
            })

    return available


class SlotUnavailableError(Exception):
    """
    Выбрасывается, когда время, которое пытается забронировать
    клиент, оказалось недоступно к моменту фактического создания
    записи — например, его успел занять кто-то другой, мастер
    больше не оказывает эту услугу, или день закрылся исключением.
    """


def create_booking(
    master: Master,
    service: Service,
    target_date: date,
    start_time: time,
    client_name: str,
    client_phone: str,
    source: str = Booking.Source.ONLINE,
    comment: str = "",
    slot_step_minutes: int = 15,
):
    """
    Создаёт запись клиента, заново проверяя доступность слота
    внутри транзакции с блокировкой мастера.

    Между тем, как клиент увидел свободное время на экране,
    и тем, как он нажал "подтвердить", это время мог занять кто-то
    другой. Чтобы два клиента не забронировали один и тот же слот
    одновременно, мы блокируем строку мастера (select_for_update)
    на время проверки и создания записи: пока одна транзакция не
    завершится, вторая будет ждать на этой строке и, дождавшись,
    увидит уже актуальную занятость мастера.

    Блокировать саму таблицу Booking недостаточно: если на слот
    ещё нет ни одной записи, SELECT ... FOR UPDATE по Booking
    просто не найдёт, что блокировать, и не помешает второй,
    параллельной вставке.

    Бросает SlotUnavailableError, если слот недоступен по любой
    причине. Ничего не создаёт в этом случае.
    """

    with transaction.atomic():
        locked_master = Master.objects.select_for_update().get(
            pk=master.pk,
        )

        try:
            master_service = locked_master.master_services.get(
                service=service,
                is_active=True,
            )
        except MasterService.DoesNotExist:
            raise SlotUnavailableError(
                "Мастер не оказывает данную услугу.",
            )

        available_slots = get_available_slots(
            locked_master,
            service,
            target_date,
            slot_step_minutes,
        )

        if start_time not in available_slots:
            raise SlotUnavailableError(
                "Выбранное время больше недоступно.",
            )

        booking = Booking.objects.create(
            master=locked_master,
            service=service,
            date=target_date,
            start_time=start_time,
            client_name=client_name,
            client_phone=client_phone,
            price=master_service.price,
            duration=master_service.duration,
            status=Booking.Status.NEW,
            source=source,
            comment=comment,
        )

    return booking
