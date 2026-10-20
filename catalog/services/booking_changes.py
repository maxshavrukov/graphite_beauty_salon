"""
Изменение существующей записи: смена статуса и перенос.

Всё, что меняет запись после создания, проходит через этот модуль:
форма и действия в админке, а позже и уведомления клиентам. Здесь
правила переходов между статусами, блокировка строк против гонки и
журнал (BookingEvent) — кто, когда и что изменил.

Создание записи живёт в booking.py и сюда не входит.
"""

from datetime import date, time

from django.db import transaction

from ..models import Booking, BookingEvent, Master, MasterService, Service
from .booking import validate_booking_slot


class BookingStateError(Exception):
    """
    Запись сейчас нельзя изменить так, как просят: переход статуса не
    разрешён или запись уже закрыта (отменена, завершена, неявка).
    """


def can_change_status(old_status: str, new_status: str) -> bool:
    """Можно ли перевести запись из old_status в new_status."""
    try:
        status_key = Booking.Status(old_status)
    except ValueError:
        return False
    return new_status in Booking.ALLOWED_TRANSITIONS.get(status_key, ())


def _status_label(status: str) -> str:
    # Безопасное получение текстовой метки статуса для Pylance и Django
    for choice, label in Booking.Status.choices:
        if choice == status:
            return str(label)
    return str(status)


def _booking_pk(booking: Booking | int) -> int:
    return booking.pk if isinstance(booking, Booking) else booking


def change_booking_status(
    booking: Booking | int,
    new_status: str,
    *,
    actor=None,
    note: str = "",
) -> Booking:
    """
    Меняет статус записи по таблице Booking.ALLOWED_TRANSITIONS.

    Строка записи блокируется на время проверки, поэтому два админа,
    одновременно нажавших «Подтвердить» и «Отменить», не перезапишут
    друг друга: второй получит BookingStateError.

    Возвращает свежую запись из базы. actor — сотрудник (для журнала).
    """
    with transaction.atomic():
        locked = Booking.objects.select_for_update().get(
            pk=_booking_pk(booking),
        )
        old_status = locked.status

        if not can_change_status(old_status, new_status):
            raise BookingStateError(
                f"Нельзя перевести запись из статуса "
                f"«{_status_label(old_status)}» "
                f"в «{_status_label(new_status)}».",
            )

        locked.status = new_status
        locked.save(update_fields=["status", "updated_at"])

        BookingEvent.objects.create(
            booking=locked,
            kind=BookingEvent.Kind.STATUS,
            actor=actor,
            from_status=old_status,
            to_status=new_status,
            details=note,
        )

    return locked


def validate_reschedule(
    booking: Booking,
    *,
    master: Master,
    service: Service,
    target_date: date,
    start_time: time,
) -> MasterService:
    """
    Проверяет, можно ли поставить запись на новое место. Ничего не меняет.

    Администратор может поставить запись вне обычных рабочих дней, но не
    на отсутствие, блокировку времени или поверх другой активной записи.
    Саму переносимую запись исключаем из проверки. Если мастер и услуга не
    меняются, сохраняем возможность переноса даже после деактивации этой
    пары: уже обещанную клиенту запись нельзя сделать непереносимой только
    из-за изменения каталога.
    """
    same_pair = (
        master.pk == booking.master_id and service.pk == booking.service_id
    )

    return validate_booking_slot(
        master,
        service,
        target_date,
        start_time,
        Booking.Source.ADMIN,
        exclude_booking_id=booking.pk,
        duration_minutes=booking.duration if same_pair else None,
        allow_inactive_existing_pair=same_pair,
    )


def _describe_changes(old: Booking, new_values: dict) -> str:
    """Текст для журнала: что именно изменилось."""
    parts = []

    if new_values["master"].pk != old.master_id:
        parts.append(f"Мастер: {old.master} → {new_values['master']}")

    if new_values["service"].pk != old.service_id:
        parts.append(f"Услуга: {old.service} → {new_values['service']}")

    if new_values["date"] != old.date:
        parts.append(f"Дата: {old.date:%d.%m.%Y} → {new_values['date']:%d.%m.%Y}")

    if new_values["start_time"] != old.start_time:
        parts.append(
            f"Время: {old.start_time:%H:%M} → {new_values['start_time']:%H:%M}",
        )

    return "; ".join(parts)


def reschedule_booking(
    booking: Booking | int,
    *,
    master: Master | None = None,
    service: Service | None = None,
    target_date: date | None = None,
    start_time: time | None = None,
    actor=None,
    note: str = "",
) -> Booking:
    """
    Переносит или изменяет существующую запись, не меняя её статус.

    Запись блокируется отдельно от связанных таблиц, затем блокировки
    мастеров (старого и нового) захватываются строго по возрастанию pk.
    Это даёт единый порядок блокировок для встречных переносов A→B и B→A.
    Проверка слота и запись события выполняются в одной транзакции.
    """
    with transaction.atomic():
        # Важно ограничить блокировку самой записью. Без of=("self",)
        # PostgreSQL может заблокировать строки из select_related, что вместе
        # с блокировкой целевого мастера создаёт риск deadlock.
        locked = (
            Booking.objects.select_for_update(of=("self",))
            .get(pk=_booking_pk(booking))
        )

        if locked.status not in Booking.ACTIVE_STATUSES:
            raise BookingStateError(
                f"Запись в статусе «{_status_label(locked.status)}» "
                "не редактируется. Создайте новую запись.",
            )

        new_master_id = master.pk if master is not None else locked.master_id
        new_service_id = service.pk if service is not None else locked.service_id
        new_date = target_date if target_date is not None else locked.date
        new_start_time = start_time if start_time is not None else locked.start_time

        if (
            new_master_id == locked.master_id
            and new_service_id == locked.service_id
            and new_date == locked.date
            and new_start_time == locked.start_time
        ):
            return locked

        # Все мастера, участвующие в переносе, блокируются в одном порядке.
        # При двух одновременных встречных переносах это не позволяет одной
        # транзакции взять A→B, а другой — B→A в противоположном порядке.
        master_ids = sorted({locked.master_id, new_master_id})
        locked_masters = {}
        for master_id in master_ids:
            locked_masters[master_id] = Master.objects.select_for_update().get(
                pk=master_id,
            )

        old_master = locked_masters[locked.master_id]
        new_master = locked_masters[new_master_id]
        new_service = Service.objects.get(pk=new_service_id)

        # Загружаем связанные объекты после блокировок и сохраняем их в кэше
        # связи, чтобы история изменений не делала лишние lazy queries.
        locked.master = old_master
        locked.service = Service.objects.get(pk=locked.service_id)

        new_values = {
            "master": new_master,
            "service": new_service,
            "date": new_date,
            "start_time": new_start_time,
        }

        master_service = validate_reschedule(
            locked,
            master=new_master,
            service=new_service,
            target_date=new_date,
            start_time=new_start_time,
        )

        details = _describe_changes(locked, new_values)
        if note:
            details = f"{details}. {note}" if details else note

        keeps_price_list = (
            new_master.pk == locked.master_id
            and new_service.pk == locked.service_id
        )

        locked.master = new_master
        locked.service = new_service
        locked.date = new_date
        locked.start_time = new_start_time

        if not keeps_price_list:
            locked.price = master_service.price
            locked.duration = master_service.duration

        locked.save(
            update_fields=[
                "master",
                "service",
                "date",
                "start_time",
                "price",
                "duration",
                "updated_at",
            ],
        )

        BookingEvent.objects.create(
            booking=locked,
            kind=BookingEvent.Kind.RESCHEDULED,
            actor=actor,
            from_status=locked.status,
            to_status=locked.status,
            details=details,
        )

    return locked
