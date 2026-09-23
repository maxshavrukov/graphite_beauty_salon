from datetime import date, time

from django.test import TestCase

from catalog.models import Booking, Master, Service, ServiceCategory
from catalog.services import filter_candidates_by_bookings, get_active_bookings

class FilterCandidatesByBookingsTests(TestCase):
    def test_new_booking_blocks_overlapping_candidate(self):
        category = ServiceCategory.objects.create(
            name="Тестовая категория",
            slug="test-category",
        )
        service = Service.objects.create(
            category=category,
            name="Тестовая услуга",
            slug="test-service",
        )
        master = Master.objects.create(
            name="Тестовый мастер",
            slug="test-master",
        )

        booking = Booking.objects.create(
            master=master,
            service=service,
            date=date(2026, 9, 7),
            start_time=time(10, 15),
            client_name="Тестовый клиент",
            client_phone="0000000000",
            price=500,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        candidates = [time(10, 0)]

        result = filter_candidates_by_bookings(
            candidates,
            [booking],
            service_duration_minutes=30,
        )

        self.assertEqual(result, [])

    def test_confirmed_booking_blocks_overlapping_candidate(self):
        category = ServiceCategory.objects.create(
            name="Тестовая категория",
            slug="test-category",
        )
        service = Service.objects.create(
            category=category,
            name="Тестовая услуга",
            slug="test-service",
        )
        master = Master.objects.create(
            name="Тестовый мастер",
            slug="test-master",
        )

        booking = Booking.objects.create(
            master=master,
            service=service,
            date=date(2026, 9, 7),
            start_time=time(10, 15),
            client_name="Тестовый клиент",
            client_phone="0000000000",
            price=500,
            duration=30,
            status=Booking.Status.CONFIRMED,
            source=Booking.Source.ONLINE,
        )

        candidates = [time(10, 0)]

        result = filter_candidates_by_bookings(
            candidates,
            [booking],
            service_duration_minutes=30,
        )

        self.assertEqual(result, [])

    def test_booking_touching_candidate_boundary_does_not_block(self):
        category = ServiceCategory.objects.create(
            name="Тестовая категория",
            slug="test-category",
        )
        service = Service.objects.create(
            category=category,
            name="Тестовая услуга",
            slug="test-service",
        )
        master = Master.objects.create(
            name="Тестовый мастер",
            slug="test-master",
        )

        booking = Booking.objects.create(
            master=master,
            service=service,
            date=date(2026, 9, 7),
            start_time=time(10, 0),
            client_name="Тестовый клиент",
            client_phone="0000000000",
            price=500,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        candidates = [time(10, 30)]

        result = filter_candidates_by_bookings(
            candidates,
            [booking],
            service_duration_minutes=30,
        )

        self.assertEqual(result, [time(10, 30)])

    def test_booking_duration_blocks_later_candidate(self):
        category = ServiceCategory.objects.create(
            name="Тестовая категория",
            slug="test-category",
        )
        service = Service.objects.create(
            category=category,
            name="Тестовая услуга",
            slug="test-service",
        )
        master = Master.objects.create(
            name="Тестовый мастер",
            slug="test-master",
        )

        booking = Booking.objects.create(
            master=master,
            service=service,
            date=date(2026, 9, 7),
            start_time=time(10, 0),
            client_name="Тестовый клиент",
            client_phone="0000000000",
            price=500,
            duration=60,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        candidates = [time(10, 45)]

        result = filter_candidates_by_bookings(
            candidates,
            [booking],
            service_duration_minutes=30,
        )

        self.assertEqual(result, [])


    def test_get_active_bookings_returns_only_new_and_confirmed(self):
        category = ServiceCategory.objects.create(
            name="Тестовая категория",
            slug="test-category",
        )
        service = Service.objects.create(
            category=category,
            name="Тестовая услуга",
            slug="test-service",
        )
        master = Master.objects.create(
            name="Тестовый мастер",
            slug="test-master",
        )

        for status, start_time in [
            (Booking.Status.NEW, time(10, 0)),
            (Booking.Status.CONFIRMED, time(11, 0)),
            (Booking.Status.CANCELLED, time(12, 0)),
            (Booking.Status.COMPLETED, time(13, 0)),
        ]:
            Booking.objects.create(
                master=master,
                service=service,
                date=date(2026, 9, 7),
                start_time=start_time,
                client_name="Тестовый клиент",
                client_phone="0000000000",
                price=500,
                duration=30,
                status=status,
                source=Booking.Source.ONLINE,
            )

        result = get_active_bookings(
            master,
            date(2026, 9, 7),
        )

        self.assertEqual(
            list(result.values_list("status", flat=True)),
            [
                Booking.Status.NEW,
                Booking.Status.CONFIRMED,
            ],
        )

    def test_get_active_bookings_filters_by_master_and_date(self):
        category = ServiceCategory.objects.create(
            name="Тестовая категория",
            slug="test-category-2",
        )
        service = Service.objects.create(
            category=category,
            name="Тестовая услуга",
            slug="test-service-2",
        )
        master = Master.objects.create(
            name="Тестовый мастер",
            slug="test-master-2",
        )
        another_master = Master.objects.create(
            name="Другой мастер",
            slug="another-master",
        )

        Booking.objects.create(
            master=master,
            service=service,
            date=date(2026, 9, 7),
            start_time=time(10, 0),
            client_name="Нужная запись",
            client_phone="0000000000",
            price=500,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        Booking.objects.create(
            master=another_master,
            service=service,
            date=date(2026, 9, 7),
            start_time=time(11, 0),
            client_name="Другой мастер",
            client_phone="0000000000",
            price=500,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        Booking.objects.create(
            master=master,
            service=service,
            date=date(2026, 9, 8),
            start_time=time(12, 0),
            client_name="Другая дата",
            client_phone="0000000000",
            price=500,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        result = get_active_bookings(
            master,
            date(2026, 9, 7),
        )

        self.assertEqual(result.count(), 1)
        self.assertEqual(
            result.first().client_name,
            "Нужная запись",
        )