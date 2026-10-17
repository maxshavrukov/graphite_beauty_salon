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
    return new_status in Booking.ALLOWED_TRANSITIONS.get(old_status, ())


def _status_label(status: str) -> str:
    return str(Booking.Status(status).label)


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

    Правила те же, что у админской записи: можно вне рабочих дней мастера
    (решает администратор), но нельзя на отпуск и больничный, на
    блокировку времени и поверх чужой записи. Сама переносимая запись
    себе не мешает.

    Если мастер и услуга те же, длительность берётся из самой записи,
    а не из текущего прайса: клиенту обещали именно её.
    """
    keeps_price_list = (
        master.pk == booking.master_id and service.pk == booking.service_id
    )

    return validate_booking_slot(
        master,
        service,
        target_date,
        start_time,
        Booking.Source.ADMIN,
        exclude_booking_id=booking.pk,
        duration_minutes=booking.duration if keeps_price_list else None,
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
    Переносит или изменяет запись: мастера, услугу, дату, время.
    Не переданное остаётся как было.

    Статус не меняется. Подтверждённая запись после переноса остаётся
    подтверждённой, потому что админ договорился с клиентом по телефону.
    Новая запись остаётся новой, и админ подтверждает её отдельно.

    Цена и длительность остаются прежними, пока мастер и услуга те же.
    Если их сменили, берутся из прайса нового мастера.

    Работает под блокировкой записи и нового мастера (так же, как
    create_booking), так что гонка с онлайн-записью исключена. Если
    нового времени нет, бросает SlotUnavailableError, ничего не меняя.
    Закрытую запись изменить нельзя: BookingStateError.
    """
    with transaction.atomic():
        locked = Booking.objects.select_for_update().select_related(
            "master", "service",
        ).get(pk=_booking_pk(booking))

        if locked.status not in Booking.ACTIVE_STATUSES:
            raise BookingStateError(
                f"Запись в статусе «{_status_label(locked.status)}» "
                "не редактируется. Создайте новую запись.",
            )

        new_values = {
            "master": master or locked.master,
            "service": service or locked.service,
            "date": target_date or locked.date,
            "start_time": start_time or locked.start_time,
        }

        if (
            new_values["master"].pk == locked.master_id
            and new_values["service"].pk == locked.service_id
            and new_values["date"] == locked.date
            and new_values["start_time"] == locked.start_time
        ):
            return locked

        # Блокируем нового мастера: ровно то, что делает create_booking.
        locked_master = Master.objects.select_for_update().get(
            pk=new_values["master"].pk,
        )

        master_service = validate_reschedule(
            locked,
            master=locked_master,
            service=new_values["service"],
            target_date=new_values["date"],
            start_time=new_values["start_time"],
        )

        details = _describe_changes(locked, new_values)
        if note:
            details = f"{details}. {note}" if details else note

        keeps_price_list = (
            locked_master.pk == locked.master_id
            and new_values["service"].pk == locked.service_id
        )

        locked.master = locked_master
        locked.service = new_values["service"]
        locked.date = new_values["date"]
        locked.start_time = new_values["start_time"]

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
