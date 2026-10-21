from datetime import datetime, timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import ParseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Master, MasterService, Service, ServiceCategory
from .throttles import BookingCreateThrottle
from .serializers import (
    AvailableMasterSerializer,
    BookingCreateSerializer,
    BookingSerializer,
    MasterSerializer,
    MasterServiceSerializer,
    ServiceCategorySerializer,
)
from .services import (
    SlotUnavailableError,
    get_available_dates_for_master,
    get_available_dates_for_service,
    get_available_masters_for_slot,
    get_available_slots,
    get_available_times_for_service,
    get_slot_step,
)


@api_view(["GET"])
def category_list(request):
    """
    GET /api/categories/

    Категории услуг со вложенными активными услугами — то, что
    клиент видит на первом шаге записи (и "быстрой", и "к мастеру").
    """
    categories = ServiceCategory.objects.filter(
        is_active=True,
    ).order_by("sort_order", "name")

    serializer = ServiceCategorySerializer(categories, many=True)

    return Response(serializer.data)


@api_view(["GET"])
def master_list(request):
    """
    GET /api/masters/

    Список активных мастеров — для сценария "сначала выбрать
    мастера, потом услугу".
    """
    masters = Master.objects.filter(
        is_active=True,
    ).order_by("sort_order", "name")

    serializer = MasterSerializer(
        masters, many=True, context={"request": request},
    )

    return Response(serializer.data)


@api_view(["GET"])
def master_services(request, slug):
    """
    GET /api/masters/<slug>/services/

    Какие услуги оказывает конкретный мастер, с ценой и
    длительностью у него лично.
    """
    master = get_object_or_404(Master, slug=slug, is_active=True)

    services = master.master_services.filter(
        is_active=True,
        service__is_active=True,
    ).select_related("service").order_by(
        "service__sort_order", "service__name",
    )

    serializer = MasterServiceSerializer(services, many=True)

    return Response(serializer.data)


def _get_active_master_and_service(master_slug, service_slug):
    """
    Достаёт мастера и услугу, проверяя заодно, что мастер реально
    оказывает эту услугу (есть активная MasterService). Если
    комбинация невалидна — 404, а не молчаливый пустой список:
    это ошибка в самом запросе, а не "просто нет свободного времени".
    """
    master = get_object_or_404(Master, slug=master_slug, is_active=True)
    service = get_object_or_404(Service, slug=service_slug, is_active=True)

    get_object_or_404(
        MasterService,
        master=master,
        service=service,
        is_active=True,
    )

    return master, service


def _get_active_service(service_slug):
    return get_object_or_404(Service, slug=service_slug, is_active=True)


def _parse_date_param(request):
    """
    Разбирает и валидирует ?date=YYYY-MM-DD из query-параметров.

    Возвращает date при успехе. При ошибке бросает ParseError —
    DRF сам превратит его в 400 с телом {"detail": "..."}, так что
    вызывающей вьюхе не нужно ничего дополнительно проверять или
    возвращать: если функция вернулась, значит дата валидна.
    """
    raw_date = request.query_params.get("date")

    if raw_date is None:
        raise ParseError("Параметр date обязателен.")

    try:
        target_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        raise ParseError("Дата должна быть в формате YYYY-MM-DD.")

    today = timezone.localdate()
    max_date = today + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD)

    if not (today <= target_date <= max_date):
        raise ParseError("Дата вне доступного окна записи.")

    return target_date


def _parse_time_param(request):
    """
    Разбирает ?time=HH:MM. Возвращает time при успехе, иначе —
    ParseError (см. docstring _parse_date_param).
    """
    raw_time = request.query_params.get("time")

    if raw_time is None:
        raise ParseError("Параметр time обязателен.")

    try:
        return datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        raise ParseError("Время должно быть в формате HH:MM.")


@api_view(["GET"])
def master_service_available_dates(request, slug, service_slug):
    """
    GET /api/masters/<slug>/services/<service_slug>/available-dates/

    Даты в ближайшие BOOKING_MAX_DAYS_AHEAD дней, на которые у
    ЭТОГО мастера есть свободное время по этой услуге.
    """
    master, service = _get_active_master_and_service(slug, service_slug)

    date_from = timezone.localdate()
    date_to = date_from + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD)

    dates = get_available_dates_for_master(
        master, service, date_from, date_to, slot_step_minutes=get_slot_step(),
    )

    return Response([d.isoformat() for d in dates])


@api_view(["GET"])
def master_service_available_times(request, slug, service_slug):
    """
    GET /api/masters/<slug>/services/<service_slug>/available-times/?date=YYYY-MM-DD

    Свободное время этого мастера по этой услуге на конкретную дату.
    """
    master, service = _get_active_master_and_service(slug, service_slug)

    target_date = _parse_date_param(request)

    times = get_available_slots(
        master, service, target_date, slot_step_minutes=get_slot_step(),
    )

    return Response([t.strftime("%H:%M") for t in times])


@api_view(["GET"])
def service_available_dates(request, service_slug):
    """
    GET /api/services/<service_slug>/available-dates/

    Быстрая запись, шаг "дата": даты в ближайшие
    BOOKING_MAX_DAYS_AHEAD дней, на которые есть свободный слот
    хотя бы у ОДНОГО из мастеров, оказывающих услугу.
    """
    service = _get_active_service(service_slug)

    date_from = timezone.localdate()
    date_to = date_from + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD)

    dates = get_available_dates_for_service(
        service, date_from, date_to, slot_step_minutes=get_slot_step(),
    )

    return Response([d.isoformat() for d in dates])


@api_view(["GET"])
def service_available_times(request, service_slug):
    """
    GET /api/services/<service_slug>/available-times/?date=YYYY-MM-DD

    Быстрая запись, шаг "время": объединённое время всех мастеров,
    оказывающих услугу, на конкретную дату.
    """
    service = _get_active_service(service_slug)

    target_date = _parse_date_param(request)

    times = get_available_times_for_service(
        service, target_date, slot_step_minutes=get_slot_step(),
    )

    return Response([t.strftime("%H:%M") for t in times])


@api_view(["GET"])
def service_available_masters(request, service_slug):
    """
    GET /api/services/<service_slug>/available-masters/?date=YYYY-MM-DD&time=HH:MM

    Быстрая запись, финальный шаг: список мастеров, свободных
    именно в это время, вместе с ценой у каждого — то самое
    "Виктор 450 / Анжелика 600".
    """
    service = _get_active_service(service_slug)

    target_date = _parse_date_param(request)
    target_time = _parse_time_param(request)

    available = get_available_masters_for_slot(
        service, target_date, target_time, slot_step_minutes=get_slot_step(),
    )

    serializer = AvailableMasterSerializer(
        available, many=True, context={"request": request},
    )

    return Response(serializer.data)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([BookingCreateThrottle])
def booking_create(request):
    """
    POST /api/bookings/

    Публичная запись клиента. Создаётся со статусом NEW и
    источником ONLINE — дальше её должен подтвердить администратор.

    Авторизация отключена намеренно: клиенту сайта не нужен аккаунт,
    и если владелец сидит в админке в том же браузере, сессия не
    должна влиять на публичную форму (например, требовать CSRF).

    Ответы:
      201 — запись создана;
      400 — некорректные данные (нет такого мастера, плохой телефон...);
      409 — время уже занято или стало недоступно.
    """
    serializer = BookingCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        booking = serializer.save()
    except SlotUnavailableError as error:
        return Response({"detail": str(error)}, status=409)

    return Response(BookingSerializer(booking).data, status=201)
