"""
ИЗМЕРЕНИЕ: сколько запросов к базе делает расчёт свободного времени.

Эти тесты ничего не проверяют по сути — они считают запросы и печатают
числа. Запускать так, чтобы вывод был виден:

    pytest catalog/tests/test_availability_query_count.py -s

Диапазон дат берётся так же, как у эндпоинтов: от сегодня на
BOOKING_MAX_DAYS_AHEAD дней вперёд.
"""

from datetime import time, timedelta

from django.conf import settings
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog.models import Absence, TimeBlock
from catalog.services import (
    get_available_dates_for_master,
    get_available_dates_for_service,
    get_available_masters_for_slot,
    get_available_times_for_service,
)
from catalog.tests.factories import (
    make_absence,
    make_booking,
    make_master,
    make_master_service,
    make_service,
    make_work_day,
)

MON_TO_SAT = [0, 1, 2, 3, 4, 5]


def make_working_master(service, weekdays, date_from, date_to):
    """Мастер, который оказывает услугу и имеет рабочие дни 09:00–18:00."""
    master = make_master()
    make_master_service(master, service, price=500, duration=30)

    current = date_from
    while current <= date_to:
        if current.weekday() in weekdays:
            make_work_day(master, current, time(9, 0), time(18, 0))
        current += timedelta(days=1)

    return master


def add_typical_load(master, service, first_day):
    """Немного «жизни»: отгул, обеды и несколько записей."""
    make_absence(
        master,
        first_day + timedelta(days=3),
        kind=Absence.Kind.DAY_OFF,
    )

    for offset in (1, 2, 5):
        TimeBlock.objects.create(
            master=master,
            date=first_day + timedelta(days=offset),
            start_time=time(13, 0),
            end_time=time(14, 0),
            reason="Обед",
        )

    for offset, hour in ((1, 10), (2, 11), (4, 15)):
        make_booking(
            master=master,
            service=service,
            target_date=first_day + timedelta(days=offset),
            start_time=time(hour, 0),
            duration=30,
        )


class AvailabilityQueryCountTests(TestCase):
    def setUp(self):
        self.service = make_service()
        self.date_from = timezone.localdate()
        self.date_to = self.date_from + timedelta(
            days=settings.BOOKING_MAX_DAYS_AHEAD,
        )

    def measure(self, title, function):
        with CaptureQueriesContext(connection) as context:
            result = function()

        days = (self.date_to - self.date_from).days + 1
        print(f"\n  >>> {title}: {len(context)} запросов (дней в календаре: {days})")
        return result

    # --- Календарь на месяц (самое тяжёлое) ----------------------------

    def test_calendar_for_one_master(self):
        master = make_working_master(
            self.service, MON_TO_SAT, self.date_from, self.date_to,
        )
        add_typical_load(master, self.service, self.date_from)

        dates = self.measure(
            "Календарь «к мастеру» (1 мастер)",
            lambda: get_available_dates_for_master(
                master, self.service, self.date_from, self.date_to,
            ),
        )

        self.assertTrue(dates)

    def test_calendar_for_service_when_all_masters_are_free(self):
        for _ in range(3):
            master = make_working_master(
                self.service, MON_TO_SAT, self.date_from, self.date_to,
            )
            add_typical_load(master, self.service, self.date_from)

        dates = self.measure(
            "Календарь «быстрая запись» (3 мастера, все работают пн–сб)",
            lambda: get_available_dates_for_service(
                self.service, self.date_from, self.date_to,
            ),
        )

        self.assertTrue(dates)

    def test_calendar_for_service_when_masters_work_on_different_days(self):
        schedules = ([0, 1], [2, 3], [4, 5])  # у каждого мастера свои дни

        for weekdays in schedules:
            master = make_working_master(
                self.service, weekdays, self.date_from, self.date_to,
            )
            add_typical_load(master, self.service, self.date_from)

        dates = self.measure(
            "Календарь «быстрая запись» (3 мастера, у каждого свои дни)",
            lambda: get_available_dates_for_service(
                self.service, self.date_from, self.date_to,
            ),
        )

        self.assertTrue(dates)

    def test_calendar_for_service_with_five_masters_on_different_days(self):
        schedules = ([0], [1, 2], [3], [4], [5])

        for weekdays in schedules:
            master = make_working_master(
                self.service, weekdays, self.date_from, self.date_to,
            )
            add_typical_load(master, self.service, self.date_from)

        dates = self.measure(
            "Календарь «быстрая запись» (5 мастеров, у каждого свои дни)",
            lambda: get_available_dates_for_service(
                self.service, self.date_from, self.date_to,
            ),
        )

        self.assertTrue(dates)

    # --- Один день (для сравнения) --------------------------------------

    def test_times_for_service_on_one_day(self):
        for _ in range(3):
            make_working_master(
                self.service, MON_TO_SAT, self.date_from, self.date_to,
            )

        target_date = self.date_from + timedelta(days=1)

        times = self.measure(
            "Время на один день, быстрая запись (3 мастера)",
            lambda: get_available_times_for_service(self.service, target_date),
        )

        self.assertIsInstance(times, list)

    def test_masters_for_one_slot(self):
        for _ in range(3):
            make_working_master(
                self.service, MON_TO_SAT, self.date_from, self.date_to,
            )

        target_date = self.date_from + timedelta(days=1)

        masters = self.measure(
            "Мастера на конкретное время (3 мастера)",
            lambda: get_available_masters_for_slot(
                self.service, target_date, time(10, 0),
            ),
        )

        self.assertIsInstance(masters, list)
