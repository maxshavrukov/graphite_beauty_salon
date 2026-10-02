"""
Небольшие фабрики для тестов каталога.

Убирают повторяющееся создание категории/услуги/мастера в каждом
тесте. Slug по умолчанию генерируется с уникальным счётчиком, чтобы
можно было создать несколько мастеров/услуг в одном тесте без
конфликта UniqueConstraint — если нужен конкретный slug, просто
передай его явно.
"""

import itertools
from datetime import date, time
from decimal import Decimal
from typing import Optional, Union

from catalog.models import (
    Booking,
    Master,
    MasterService,
    Service,
    ServiceCategory,
)

_counter = itertools.count(1)

# DecimalField у нас принимает и Decimal, и int (Django сам
# приводит), но раз мы даём это как параметр наружу — явно
# разрешаем оба варианта, а не даём Pylance гадать по дефолту.
Money = Union[Decimal, int, str]


def make_category(
    name: Optional[str] = None,
    slug: Optional[str] = None,
    **kwargs,
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
    **kwargs,
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
    **kwargs,
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
    price: Money = 500,
    duration: int = 30,
    **kwargs,
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
    target_date: Optional[date] = None,
    start_time: Optional[time] = None,
    duration: int = 30,
    price: Money = 500,
    client_name: str = "Тестовый клиент",
    client_phone: str = "0000000000",
    status: str = Booking.Status.NEW,
    source: str = Booking.Source.ONLINE,
    **kwargs,
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
