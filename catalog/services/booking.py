"""
Создание записи клиента.

Единственное место в проекте, которое реально создаёт записи Booking
(админка тоже пользуется create_booking и не пишет в таблицу напрямую).
Здесь же — повторная проверка доступности слота внутри транзакции
с блокировкой мастера, защищающая от гонки при одновременных
попытках записи.

Сами правила «можно ли записать на это время» вынесены в отдельную
функцию validate_booking_slot: её вызывает и create_booking, и админка
(чтобы показать ошибку в форме до сохранения).
"""

from datetime import date, datetime, time, timedelta

from django.db import transaction

from ..models import Booking, BookingEvent, Master, MasterService, Service
from .scheduling import get_active_bookings, get_available_slots, intervals_overlap


class SlotUnavailableError(Exception):
    """
    Выбрасывается, когда время, которое пытается забронировать
    клиент, оказалось недоступно к моменту фактического создания
    записи — например, его успел занять кто-то другой, мастер
    больше не оказывает эту услугу, или день закрылся исключением.
    """


def get_booking_end_time(
    start_time: time,
    duration_minutes: int,
) -> time:
    """
    Возвращает время окончания услуги.

    Запись не может пересекать полночь, потому что Booking хранит
    дату и start_time как значения одного календарного дня.
    """

    end_datetime = (
        datetime.combine(date.min, start_time)
        + timedelta(minutes=duration_minutes)
    )

    if end_datetime.date() != date.min:
        raise SlotUnavailableError(
            "Услуга не может пересекать полночь.",
        )

    return end_datetime.time()


def validate_booking_slot(
    master: Master,
    service: Service,
    target_date: date,
    start_time: time,
    source: str = Booking.Source.ONLINE,
    slot_step_minutes: int = 15,
    *,
    exclude_booking_id: int | None = None,
    duration_minutes: int | None = None,
) -> MasterService:
    """
    Проверяет, можно ли создать такую запись. Ничего не создаёт.

    Возвращает MasterService мастера для этой услуги — из него
    берутся цена и длительность. Если записать нельзя, выбрасывает
    SlotUnavailableError с понятным текстом.

    ONLINE:
        - только время рабочих дней мастера (WorkDay);
        - только доступные кандидаты;
        - учитываются TimeBlock и активные Booking.

    PHONE / ADMIN:
        - могут быть созданы вне рабочего расписания;
        - но не могут пересекаться с TimeBlock;
        - не могут пересекаться с активными Booking;
        - дни отсутствия мастера (отпуск, больничный, отгул)
          остаются закрытыми для всех источников.

    exclude_booking_id и duration_minutes нужны переносу существующей
    записи (reschedule_booking) и только для PHONE / ADMIN:

        - exclude_booking_id — эта запись не считается занятым временем,
          иначе при переносе она мешала бы сама себе;
        - duration_minutes — проверять по длительности самой записи
          (она сохранена при создании), а не по текущему прайсу мастера.

    create_booking вызывает эту функцию внутри транзакции, когда мастер
    уже заблокирован, — тогда проверка надёжна. Вызов из формы админки
    без блокировки нужен только для понятной ошибки заранее: если в
    последний момент время всё же займут, create_booking это поймает.
    """

    if source not in Booking.Source.values:
        raise ValueError(
            f"Недопустимый источник записи: {source}",
        )

    if source == Booking.Source.ONLINE and (
        exclude_booking_id is not None or duration_minutes is not None
    ):
        raise ValueError(
            "exclude_booking_id и duration_minutes не поддерживаются "
            "для онлайн-записи.",
        )

    if not master.is_active:
        raise SlotUnavailableError(
            "Мастер больше не принимает клиентов.",
        )

    try:
        master_service = master.master_services.get(
            service=service,
            is_active=True,
        )
    except MasterService.DoesNotExist:
        raise SlotUnavailableError(
            "Мастер не оказывает данную услугу.",
        )

    # Отсутствие (отпуск, больничный, отгул) нельзя обойти даже
    # административной записью. Неотмеченный день — другое дело:
    # клиенты времени не видят, но админ может вписать запись вручную.
    absence = master.absences.filter(
        start_date__lte=target_date,
        end_date__gte=target_date,
    ).first()

    if absence is not None:
        raise SlotUnavailableError(
            "На выбранную дату мастер не работает "
            f"({absence.get_kind_display().lower()}).",
        )

    # Проверяем, что услуга физически помещается в пределах
    # одного календарного дня.
    booking_end_time = get_booking_end_time(
        start_time,
        (
            duration_minutes
            if duration_minutes is not None
            else master_service.duration
        ),
    )

    if source == Booking.Source.ONLINE:
        # Онлайн-запись обязана пройти через стандартную
        # систему доступных слотов.
        available_slots = get_available_slots(
            master,
            service,
            target_date,
            slot_step_minutes,
        )

        if start_time not in available_slots:
            raise SlotUnavailableError(
                "Выбранное время больше недоступно.",
            )

    else:
        # PHONE / ADMIN могут работать вне обычного расписания,
        # поэтому get_available_slots() здесь использовать нельзя.

        time_blocks = master.time_blocks.filter(
            date=target_date,
        )

        has_block_overlap = any(
            intervals_overlap(
                start_time,
                booking_end_time,
                block.start_time,
                block.end_time,
            )
            for block in time_blocks
        )

        if has_block_overlap:
            raise SlotUnavailableError(
                "Выбранное время заблокировано.",
            )

        active_bookings = get_active_bookings(
            master,
            target_date,
        )

        if exclude_booking_id is not None:
            active_bookings = active_bookings.exclude(pk=exclude_booking_id)

        has_booking_overlap = any(
            intervals_overlap(
                start_time,
                booking_end_time,
                booking.start_time,
                get_booking_end_time(
                    booking.start_time,
                    booking.duration,
                ),
            )
            for booking in active_bookings
        )

        if has_booking_overlap:
            raise SlotUnavailableError(
                "Выбранное время уже занято.",
            )

    return master_service


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
    actor=None,
):
    """
    Создаёт запись клиента с повторной проверкой доступности
    внутри транзакции с блокировкой мастера.

    Правила проверки описаны в validate_booking_slot.

    При создании Booking цена и длительность берутся из
    MasterService и сохраняются как исторический snapshot.

    actor — сотрудник, создающий запись из админки (для журнала);
    для записи с сайта не передаётся.
    """

    if source not in Booking.Source.values:
        raise ValueError(
            f"Недопустимый источник записи: {source}",
        )

    with transaction.atomic():
        locked_master = Master.objects.select_for_update().get(
            pk=master.pk,
        )

        master_service = validate_booking_slot(
            locked_master,
            service,
            target_date,
            start_time,
            source,
            slot_step_minutes,
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

        BookingEvent.objects.create(
            booking=booking,
            kind=BookingEvent.Kind.CREATED,
            actor=actor,
            to_status=booking.status,
        )

    return booking
