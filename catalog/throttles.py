from rest_framework.throttling import AnonRateThrottle


class BookingCreateThrottle(AnonRateThrottle):
    """
    Ограничение на создание записей с одного IP-адреса.

    Отдельный класс (со своим scope), чтобы у создания записи был
    свой, более строгий лимит, чем у обычного просмотра каталога.
    Сам лимит (например, "10/hour") задаётся в settings.py.
    """

    scope = "booking_create"
