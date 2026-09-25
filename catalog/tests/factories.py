import itertools
from decimal import Decimal
from typing import Any, Optional

from catalog.models import (
    Booking,
    Master,
    MasterService,
    Service,
    ServiceCategory,
)

_counter = itertools.count(1)


def make_category(
    name: Optional[str] = None,
    slug: Optional[str] = None,
    **kwargs: Any,
) -> ServiceCategory:
    n = next(_counter)
    return ServiceCategory.objects.create(
        name=name or f"Категория {n}",
        slug=slug or f"category-{n}",
        **kwargs,
    )


def make_service(
    category: Optional[ServiceCategory] = None,
    name: Optional[str] = None,
    slug: Optional[str] = None,
    **kwargs: Any,
) -> Service:
    n = next(_counter)
    return Service.objects.create(
        category=category or make_category(),
        name=name or f"Услуга {n}",
        slug=slug or f"service-{n}",
        **kwargs,
    )


def make_master(
    name: Optional[str] = None,
    slug: Optional[str] = None,
    **kwargs: Any,
) -> Master:
    n = next(_counter)
    return Master.objects.create(
        name=name or f"Мастер {n}",
        slug=slug or f"master-{n}",
        **kwargs,
    )


def make_master_service(
    master: Optional[Master] = None,
    service: Optional[Service] = None,
    price: Any = Decimal("500.00"),
    duration: int = 30,
    **kwargs: Any,
) -> MasterService:
    return MasterService.objects.create(
        master=master or make_master(),
        service=service or make_service(),
        price=price,
        duration=duration,
        **kwargs,
    )


def make_booking(
    master: Optional[Master] = None,
    service: Optional[Service] = None,
    target_date: Any = None,
    start_time: Any = None,
    duration: int = 30,
    price: Any = Decimal("500.00"),
    client_name: str = "Тестовый клиент",
    client_phone: str = "0000000000",
    status: Any = Booking.Status.NEW,
    source: Any = Booking.Source.ONLINE,
    **kwargs: Any,
) -> Booking:
    return Booking.objects.create(
        master=master or make_master(),
        service=service or make_service(),
        date=target_date,
        start_time=start_time,
        duration=duration,
        price=price,
        client_name=client_name,
        client_phone=client_phone,
        status=status,
        source=source,
        **kwargs,
    )
