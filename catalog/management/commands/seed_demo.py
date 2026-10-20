"""
Демо-данные для разработки: категории, услуги, мастера, цены и рабочие дни.

    python manage.py seed_demo

Нужны, чтобы на сайте и в админке было что смотреть и «тыкать», не заводя
всё вручную. Команду можно запускать повторно: уже созданное не дублируется,
а график продлевается на ближайшие дни. Работает только при DEBUG=True,
чтобы случайно не засорить настоящий салон.
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Master,
    MasterService,
    Service,
    ServiceCategory,
    WorkDay,
)

# (slug категории, название, услуги: (slug, название, описание))
CATALOG = [
    (
        "hair",
        "Парикмахерские услуги",
        [
            ("womens-haircut", "Женская стрижка", "Консультация, мытьё и стрижка."),
            ("mens-haircut", "Мужская стрижка", "Стрижка машинкой и ножницами."),
            ("styling", "Укладка", "Укладка на каждый день или для события."),
        ],
    ),
    (
        "nails",
        "Маникюр",
        [
            ("classic-manicure", "Классический маникюр", "Уход за руками и формой ногтей."),
            ("gel-manicure", "Маникюр с покрытием", "Гель-лак, держится до трёх недель."),
        ],
    ),
    (
        "brows",
        "Брови",
        [
            ("brow-shaping", "Оформление бровей", "Коррекция формы и окрашивание."),
        ],
    ),
]

# slug мастера, имя, о себе, дни недели без работы (0 — понедельник)
MASTERS = [
    ("karina", "Карина", "Мастер маникюра и бровей.", (6,)),
    ("vadim", "Вадим", "Барбер и стилист.", (0, 6)),
    ("violeta", "Виолета", "Стилист-колорист.", (6,)),
]

# (мастер, услуга, цена, минут). У некоторых услуг по два мастера,
# чтобы на последнем шаге записи было из кого выбрать.
PRICES = [
    ("vadim", "womens-haircut", "600", 60),
    ("violeta", "womens-haircut", "800", 60),
    ("vadim", "mens-haircut", "400", 40),
    ("vadim", "styling", "500", 45),
    ("violeta", "styling", "650", 45),
    ("karina", "classic-manicure", "450", 60),
    ("karina", "gel-manicure", "700", 90),
    ("karina", "brow-shaping", "350", 30),
    ("violeta", "brow-shaping", "400", 30),
]

WORK_START = time(10, 0)
WORK_END = time(19, 0)
BREAK_START = time(14, 0)
BREAK_END = time(15, 0)

# На сколько дней вперёд заполнять график.
SCHEDULE_DAYS = 21


class Command(BaseCommand):
    help = "Создаёт демо-данные для разработки (только при DEBUG=True)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "Демо-данные создаются только при DEBUG=True. "
                "На настоящем сайте они не нужны.",
            )

        with transaction.atomic():
            services = self._create_catalog()
            masters = self._create_masters()
            self._create_prices(masters, services)
            work_days = self._create_schedule(masters)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: услуг {len(services)}, мастеров {len(masters)}, "
                f"рабочих дней продлено {work_days}.",
            ),
        )

    def _create_catalog(self):
        services = {}

        for order, (cat_slug, cat_name, items) in enumerate(CATALOG):
            category, _ = ServiceCategory.objects.get_or_create(
                slug=cat_slug,
                defaults={"name": cat_name, "sort_order": order},
            )

            for item_order, (slug, name, description) in enumerate(items):
                service, _ = Service.objects.get_or_create(
                    slug=slug,
                    defaults={
                        "category": category,
                        "name": name,
                        "description": description,
                        "sort_order": item_order,
                    },
                )
                services[slug] = service

        return services

    def _create_masters(self):
        masters = {}

        for order, (slug, name, bio, _days_off) in enumerate(MASTERS):
            master, _ = Master.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "bio": bio, "sort_order": order},
            )
            masters[slug] = master

        return masters

    def _create_prices(self, masters, services):
        for master_slug, service_slug, price, duration in PRICES:
            MasterService.objects.update_or_create(
                master=masters[master_slug],
                service=services[service_slug],
                defaults={
                    "price": Decimal(price),
                    "duration": duration,
                    "is_active": True,
                },
            )

    def _create_schedule(self, masters):
        days_off = {slug: off for slug, _n, _b, off in MASTERS}
        today = timezone.localdate()
        count = 0

        for slug, master in masters.items():
            for offset in range(SCHEDULE_DAYS):
                day: date = today + timedelta(days=offset)

                if day.weekday() in days_off[slug]:
                    continue

                _, created = WorkDay.objects.get_or_create(
                    master=master,
                    date=day,
                    defaults={
                        "start_time": WORK_START,
                        "end_time": WORK_END,
                        "break_start": BREAK_START,
                        "break_end": BREAK_END,
                    },
                )
                count += int(created)

        return count
