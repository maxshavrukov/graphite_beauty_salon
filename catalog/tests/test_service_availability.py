from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from catalog.models import WorkingHours
from catalog.services import (
    get_available_dates_for_service,
    get_available_masters_for_slot,
    get_available_times_for_service,
    get_masters_for_service,
)
from catalog.tests.factories import (
    make_booking,
    make_master,
    make_master_service,
    make_service,
)


class ServiceAvailabilityTestsBase(TestCase):
    def setUp(self):
        self.service = make_service()
        self.other_service = make_service()
        self.monday = date(2026, 9, 7)
        self.tuesday = date(2026, 9, 8)


class GetMastersForServiceTests(ServiceAvailabilityTestsBase):
    def test_returns_only_masters_offering_service(self):
        offering_master = make_master()
        other_master = make_master()
        make_master_service(offering_master, self.service)
        make_master_service(other_master, self.other_service)

        result = list(get_masters_for_service(self.service))

        self.assertEqual(result, [offering_master])

    def test_excludes_inactive_master_service(self):
        master = make_master()
        make_master_service(master, self.service, is_active=False)

        result = list(get_masters_for_service(self.service))

        self.assertEqual(result, [])

    def test_excludes_inactive_master(self):
        master = make_master(is_active=False)
        make_master_service(master, self.service)

        result = list(get_masters_for_service(self.service))

        self.assertEqual(result, [])


class GetAvailableDatesForServiceTests(ServiceAvailabilityTestsBase):
    def test_includes_date_when_one_of_several_masters_is_free(self):
        busy_master = make_master()
        free_master = make_master()

        for master in (busy_master, free_master):
            make_master_service(master, self.service, duration=30)
            WorkingHours.objects.create(
                master=master,
                weekday=WorkingHours.Weekday.MONDAY,
                start_time=time(9, 0),
                end_time=time(9, 30),
            )

        # Единственный слот занятого мастера занят бронью.
        make_booking(
            master=busy_master,
            service=self.service,
            target_date=self.monday,
            start_time=time(9, 0),
            duration=30,
        )

        result = get_available_dates_for_service(
            self.service, date_from=self.monday, date_to=self.tuesday,
        )

        self.assertIn(self.monday, result)

    def test_excludes_date_when_no_master_is_free(self):
        master = make_master()
        make_master_service(master, self.service, duration=30)
        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(9, 30),
        )
        make_booking(
            master=master,
            service=self.service,
            target_date=self.monday,
            start_time=time(9, 0),
            duration=30,
        )

        result = get_available_dates_for_service(
            self.service, date_from=self.monday, date_to=self.monday,
        )

        self.assertEqual(result, [])

    def test_excludes_date_outside_range(self):
        master = make_master()
        make_master_service(master, self.service, duration=30)
        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.TUESDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        result = get_available_dates_for_service(
            self.service, date_from=self.monday, date_to=self.monday,
        )

        self.assertEqual(result, [self.monday])
        self.assertNotIn(self.tuesday, result)

    def test_returns_empty_when_no_master_offers_service(self):
        result = get_available_dates_for_service(
            self.service, date_from=self.monday, date_to=self.tuesday,
        )

        self.assertEqual(result, [])


class GetAvailableTimesForServiceTests(ServiceAvailabilityTestsBase):
    def test_merges_times_from_different_masters(self):
        master_a = make_master()
        master_b = make_master()

        make_master_service(master_a, self.service, duration=30)
        make_master_service(master_b, self.service, price=600, duration=30)

        WorkingHours.objects.create(
            master=master_a, weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0), end_time=time(9, 30),
        )
        WorkingHours.objects.create(
            master=master_b, weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(15, 0), end_time=time(15, 30),
        )

        result = get_available_times_for_service(
            self.service, self.monday, slot_step_minutes=30,
        )

        self.assertEqual(result, [time(9, 0), time(15, 0)])

    def test_does_not_duplicate_overlapping_time(self):
        for _ in range(2):
            master = make_master()
            make_master_service(master, self.service, duration=30)
            WorkingHours.objects.create(
                master=master, weekday=WorkingHours.Weekday.MONDAY,
                start_time=time(9, 0), end_time=time(9, 30),
            )

        result = get_available_times_for_service(
            self.service, self.monday, slot_step_minutes=30,
        )

        self.assertEqual(result, [time(9, 0)])


class GetAvailableMastersForSlotTests(ServiceAvailabilityTestsBase):
    def test_returns_only_masters_free_at_exact_time_with_price(self):
        free_master = make_master()
        busy_master = make_master()

        make_master_service(free_master, self.service, price=Decimal("450.00"), duration=30)
        make_master_service(busy_master, self.service, price=Decimal("600.00"), duration=30)

        for master in (free_master, busy_master):
            WorkingHours.objects.create(
                master=master, weekday=WorkingHours.Weekday.MONDAY,
                start_time=time(9, 0), end_time=time(9, 30),
            )

        make_booking(
            master=busy_master,
            service=self.service,
            target_date=self.monday,
            start_time=time(9, 0),
            duration=30,
            price=600,
        )

        result = get_available_masters_for_slot(self.service, self.monday, time(9, 0))

        self.assertEqual(
            result, [{"master": free_master, "price": Decimal("450.00")}],
        )

    def test_ignores_master_not_offering_service(self):
        master = make_master()
        make_master_service(master, self.other_service, duration=30)
        WorkingHours.objects.create(
            master=master, weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0), end_time=time(9, 30),
        )

        result = get_available_masters_for_slot(self.service, self.monday, time(9, 0))

        self.assertEqual(result, [])

    def test_returns_empty_when_no_master_free_at_that_exact_time(self):
        master = make_master()
        make_master_service(master, self.service, duration=30)
        WorkingHours.objects.create(
            master=master, weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0), end_time=time(9, 30),
        )

        result = get_available_masters_for_slot(self.service, self.monday, time(10, 0))

        self.assertEqual(result, [])
