from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from catalog.models import (
    Booking,
    Master,
    MasterService,
    Service,
    ServiceCategory,
    WorkingHours,
)
from catalog.services import (
    get_available_dates_for_service,
    get_available_masters_for_slot,
    get_available_times_for_service,
    get_masters_for_service,
)


class ServiceAvailabilityTestsBase(TestCase):
    def setUp(self):
        self.category = ServiceCategory.objects.create(
            name="Тестовая категория",
            slug="test-category",
        )
        self.service = Service.objects.create(
            category=self.category,
            name="Тестовая услуга",
            slug="test-service",
        )
        self.other_service = Service.objects.create(
            category=self.category,
            name="Другая услуга",
            slug="other-service",
        )
        self.monday = date(2026, 9, 7)
        self.tuesday = date(2026, 9, 8)


class GetMastersForServiceTests(ServiceAvailabilityTestsBase):
    def test_returns_only_masters_offering_service(self):
        offering_master = Master.objects.create(
            name="Оказывает услугу",
            slug="offering-master",
        )
        other_master = Master.objects.create(
            name="Не оказывает услугу",
            slug="other-master",
        )
        MasterService.objects.create(
            master=offering_master,
            service=self.service,
            price=500,
            duration=30,
        )
        MasterService.objects.create(
            master=other_master,
            service=self.other_service,
            price=500,
            duration=30,
        )

        result = list(get_masters_for_service(self.service))

        self.assertEqual(result, [offering_master])

    def test_excludes_inactive_master_service(self):
        master = Master.objects.create(
            name="Мастер",
            slug="master-inactive-service",
        )
        MasterService.objects.create(
            master=master,
            service=self.service,
            price=500,
            duration=30,
            is_active=False,
        )

        result = list(get_masters_for_service(self.service))

        self.assertEqual(result, [])

    def test_excludes_inactive_master(self):
        master = Master.objects.create(
            name="Уволенный мастер",
            slug="inactive-master",
            is_active=False,
        )
        MasterService.objects.create(
            master=master,
            service=self.service,
            price=500,
            duration=30,
        )

        result = list(get_masters_for_service(self.service))

        self.assertEqual(result, [])


class GetAvailableDatesForServiceTests(ServiceAvailabilityTestsBase):
    def test_includes_date_when_one_of_several_masters_is_free(self):
        busy_master = Master.objects.create(
            name="Занятый мастер",
            slug="busy-master",
        )
        free_master = Master.objects.create(
            name="Свободный мастер",
            slug="free-master",
        )

        for master in (busy_master, free_master):
            MasterService.objects.create(
                master=master,
                service=self.service,
                price=500,
                duration=30,
            )
            WorkingHours.objects.create(
                master=master,
                weekday=WorkingHours.Weekday.MONDAY,
                start_time=time(9, 0),
                end_time=time(9, 30),
            )

        # Единственный слот занятого мастера занят бронью.
        Booking.objects.create(
            master=busy_master,
            service=self.service,
            date=self.monday,
            start_time=time(9, 0),
            client_name="Клиент",
            client_phone="0000000000",
            price=500,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        result = get_available_dates_for_service(
            self.service,
            date_from=self.monday,
            date_to=self.tuesday,
        )

        self.assertIn(self.monday, result)

    def test_excludes_date_when_no_master_is_free(self):
        master = Master.objects.create(
            name="Мастер",
            slug="master-fully-booked",
        )
        MasterService.objects.create(
            master=master,
            service=self.service,
            price=500,
            duration=30,
        )
        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(9, 30),
        )
        Booking.objects.create(
            master=master,
            service=self.service,
            date=self.monday,
            start_time=time(9, 0),
            client_name="Клиент",
            client_phone="0000000000",
            price=500,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        result = get_available_dates_for_service(
            self.service,
            date_from=self.monday,
            date_to=self.monday,
        )

        self.assertEqual(result, [])

    def test_excludes_date_outside_range(self):
        master = Master.objects.create(
            name="Мастер",
            slug="master-outside-range",
        )
        MasterService.objects.create(
            master=master,
            service=self.service,
            price=500,
            duration=30,
        )
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
            self.service,
            date_from=self.monday,
            date_to=self.monday,
        )

        self.assertEqual(result, [self.monday])
        self.assertNotIn(self.tuesday, result)

    def test_returns_empty_when_no_master_offers_service(self):
        result = get_available_dates_for_service(
            self.service,
            date_from=self.monday,
            date_to=self.tuesday,
        )

        self.assertEqual(result, [])


class GetAvailableTimesForServiceTests(ServiceAvailabilityTestsBase):
    def test_merges_times_from_different_masters(self):
        master_a = Master.objects.create(
            name="Мастер А",
            slug="master-a",
        )
        master_b = Master.objects.create(
            name="Мастер Б",
            slug="master-b",
        )

        MasterService.objects.create(
            master=master_a,
            service=self.service,
            price=500,
            duration=30,
        )
        MasterService.objects.create(
            master=master_b,
            service=self.service,
            price=600,
            duration=30,
        )

        WorkingHours.objects.create(
            master=master_a,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(9, 30),
        )
        WorkingHours.objects.create(
            master=master_b,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(15, 0),
            end_time=time(15, 30),
        )

        result = get_available_times_for_service(
            self.service,
            self.monday,
            slot_step_minutes=30,
        )

        self.assertEqual(result, [time(9, 0), time(15, 0)])

    def test_does_not_duplicate_overlapping_time(self):
        master_a = Master.objects.create(
            name="Мастер А",
            slug="master-a-dup",
        )
        master_b = Master.objects.create(
            name="Мастер Б",
            slug="master-b-dup",
        )

        for master in (master_a, master_b):
            MasterService.objects.create(
                master=master,
                service=self.service,
                price=500,
                duration=30,
            )
            WorkingHours.objects.create(
                master=master,
                weekday=WorkingHours.Weekday.MONDAY,
                start_time=time(9, 0),
                end_time=time(9, 30),
            )

        result = get_available_times_for_service(
            self.service,
            self.monday,
            slot_step_minutes=30,
        )

        self.assertEqual(result, [time(9, 0)])


class GetAvailableMastersForSlotTests(ServiceAvailabilityTestsBase):
    def test_returns_only_masters_free_at_exact_time_with_price(self):
        free_master = Master.objects.create(
            name="Виктор",
            slug="victor",
        )
        busy_master = Master.objects.create(
            name="Анжелика",
            slug="angelika",
        )

        MasterService.objects.create(
            master=free_master,
            service=self.service,
            price=Decimal("450.00"),
            duration=30,
        )
        MasterService.objects.create(
            master=busy_master,
            service=self.service,
            price=Decimal("600.00"),
            duration=30,
        )

        for master in (free_master, busy_master):
            WorkingHours.objects.create(
                master=master,
                weekday=WorkingHours.Weekday.MONDAY,
                start_time=time(9, 0),
                end_time=time(9, 30),
            )

        Booking.objects.create(
            master=busy_master,
            service=self.service,
            date=self.monday,
            start_time=time(9, 0),
            client_name="Клиент",
            client_phone="0000000000",
            price=600,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        result = get_available_masters_for_slot(
            self.service,
            self.monday,
            time(9, 0),
        )

        self.assertEqual(
            result,
            [{"master": free_master, "price": Decimal("450.00")}],
        )

    def test_ignores_master_not_offering_service(self):
        master = Master.objects.create(
            name="Мастер другой услуги",
            slug="other-service-master",
        )
        MasterService.objects.create(
            master=master,
            service=self.other_service,
            price=500,
            duration=30,
        )
        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(9, 30),
        )

        result = get_available_masters_for_slot(
            self.service,
            self.monday,
            time(9, 0),
        )

        self.assertEqual(result, [])

    def test_returns_empty_when_no_master_free_at_that_exact_time(self):
        master = Master.objects.create(
            name="Мастер",
            slug="master-no-slot",
        )
        MasterService.objects.create(
            master=master,
            service=self.service,
            price=500,
            duration=30,
        )
        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(9, 30),
        )

        result = get_available_masters_for_slot(
            self.service,
            self.monday,
            time(10, 0),
        )

        self.assertEqual(result, [])