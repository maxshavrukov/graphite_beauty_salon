"""
Агрегация доступности по всем мастерам, оказывающим услугу.

Нужно для "быстрой записи": клиент сначала выбирает услугу и дату,
не привязываясь к конкретному мастеру, и только на последнем шаге
видит, кто из мастеров свободен именно в это время.

Строится поверх scheduling.get_available_slots — здесь просто
цикл по мастерам, свою логику расчёта слотов файл не содержит.
"""

from datetime import date, time, timedelta

from ..models import Master, MasterService, Service
from .scheduling import get_available_slots, load_availability_snapshot


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


def get_available_dates_for_master(
    master: Master,
    service: Service,
    date_from: date,
    date_to: date,
    slot_step_minutes: int = 15,
):
    """
    Возвращает список дат в диапазоне [date_from, date_to]
    (включительно), на которые у КОНКРЕТНОГО мастера есть хотя бы
    один свободный слот по данной услуге.

    Используется в сценарии "сначала выбрать мастера" — в отличие
    от get_available_dates_for_service, здесь мастер уже зафиксирован
    заранее, и агрегировать по нескольким мастерам не нужно.
    """

    if date_to < date_from:
        return []

    snapshot = load_availability_snapshot(
        [master], date_from, date_to, service=service,
    )
    available_dates = []
    current = date_from

    while current <= date_to:
        if get_available_slots(
            master, service, current, slot_step_minutes, snapshot=snapshot,
        ):
            available_dates.append(current)

        current += timedelta(days=1)

    return available_dates


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

    if date_to < date_from:
        return []

    masters = list(get_masters_for_service(service))

    if not masters:
        return []

    snapshot = load_availability_snapshot(
        masters, date_from, date_to, service=service,
    )
    available_dates = []
    current = date_from

    while current <= date_to:
        has_slot = any(
            get_available_slots(
                master,
                service,
                current,
                slot_step_minutes,
                snapshot=snapshot,
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

    masters = list(get_masters_for_service(service))
    snapshot = load_availability_snapshot(
        masters, target_date, target_date, service=service,
    )

    available_times = set()

    for master in masters:
        slots = get_available_slots(
            master,
            service,
            target_date,
            slot_step_minutes,
            snapshot=snapshot,
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

    master_services = list(
        MasterService.objects.filter(
            service=service,
            is_active=True,
            master__is_active=True,
        ).select_related("master")
    )
    masters = [item.master for item in master_services]
    snapshot = load_availability_snapshot(
        masters, target_date, target_date, service=service,
    )

    available = []

    for master_service in master_services:
        slots = get_available_slots(
            master_service.master,
            service,
            target_date,
            slot_step_minutes,
            snapshot=snapshot,
        )

        if start_time in slots:
            available.append({
                "master": master_service.master,
                "price": master_service.price,
            })

    return available
