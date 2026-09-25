import threading
from datetime import date, time
from decimal import Decimal

from django.db import connection
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from catalog.models import (
    Booking,
    Master,
    MasterService,
    Service,
    ServiceCategory,
    ScheduleException,
    WorkingHours,
)
from catalog.services import SlotUnavailableError, create_booking


class CreateBookingTests(TestCase):
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
        self.master = Master.objects.create(
            name="Тестовый мастер",
            slug="test-master",
        )
        self.monday = date(2026, 9, 7)

    def test_creates_booking_with_snapshotted_price_and_duration(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=Decimal("450.00"),
            duration=30,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        booking = create_booking(
            master=self.master,
            service=self.service,
            target_date=self.monday,
            start_time=time(9, 0),
            client_name="Иван",
            client_phone="+380000000000",
        )

        self.assertEqual(booking.price, Decimal("450.00"))
        self.assertEqual(booking.duration, 30)
        self.assertEqual(booking.status, Booking.Status.NEW)
        self.assertEqual(booking.source, Booking.Source.ONLINE)
        self.assertEqual(Booking.objects.count(), 1)

    def test_price_snapshot_is_independent_from_later_price_changes(self):
        master_service = MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=Decimal("450.00"),
            duration=30,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        booking = create_booking(
            master=self.master,
            service=self.service,
            target_date=self.monday,
            start_time=time(9, 0),
            client_name="Иван",
            client_phone="+380000000000",
        )

        master_service.price = Decimal("999.00")
        master_service.save()

        booking.refresh_from_db()
        self.assertEqual(booking.price, Decimal("450.00"))

    def test_accepts_custom_source_and_comment(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=500,
            duration=30,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        booking = create_booking(
            master=self.master,
            service=self.service,
            target_date=self.monday,
            start_time=time(9, 0),
            client_name="Иван",
            client_phone="+380000000000",
            source=Booking.Source.ADMIN,
            comment="Записал администратор по телефону",
        )

        self.assertEqual(booking.source, Booking.Source.ADMIN)
        self.assertEqual(
            booking.comment,
            "Записал администратор по телефону",
        )

    def test_raises_when_master_does_not_offer_service(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        with self.assertRaises(SlotUnavailableError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(9, 0),
                client_name="Иван",
                client_phone="+380000000000",
            )

        self.assertEqual(Booking.objects.count(), 0)

    def test_raises_when_master_service_is_inactive(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=500,
            duration=30,
            is_active=False,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        with self.assertRaises(SlotUnavailableError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(9, 0),
                client_name="Иван",
                client_phone="+380000000000",
            )

        self.assertEqual(Booking.objects.count(), 0)

    def test_raises_when_day_is_closed(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=500,
            duration=30,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        ScheduleException.objects.create(
            master=self.master,
            date=self.monday,
            is_closed=True,
        )

        with self.assertRaises(SlotUnavailableError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(9, 0),
                client_name="Иван",
                client_phone="+380000000000",
            )

        self.assertEqual(Booking.objects.count(), 0)

    def test_raises_when_slot_already_taken_and_does_not_duplicate(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=500,
            duration=30,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        Booking.objects.create(
            master=self.master,
            service=self.service,
            date=self.monday,
            start_time=time(9, 0),
            client_name="Первый клиент",
            client_phone="0000000000",
            price=500,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        with self.assertRaises(SlotUnavailableError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(9, 0),
                client_name="Второй клиент",
                client_phone="1111111111",
            )

        # Ровно одна запись — попытка второго клиента не прошла.
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(
            Booking.objects.get().client_name,
            "Первый клиент",
        )


@skipUnlessDBFeature("has_select_for_update")
class CreateBookingConcurrencyTests(TransactionTestCase):
    """
    Реальный тест на гонку: два потока одновременно пытаются
    забронировать один и тот же слот у одного мастера.

    Пропускается на бэкендах без поддержки SELECT ... FOR UPDATE
    (например, SQLite) — там блокировки нет физически, и тест
    ничего бы не проверил. На Postgres (боевая БД проекта)
    выполняется по-настоящему.
    """

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
        self.master = Master.objects.create(
            name="Тестовый мастер",
            slug="test-master",
        )
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=500,
            duration=30,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        self.monday = date(2026, 9, 7)

    def test_only_one_of_two_simultaneous_bookings_succeeds(self):
        barrier = threading.Barrier(2)
        results = {}

        def attempt(name):
            # Каждому потоку — своё соединение с БД.
            connection.close()

            try:
                barrier.wait(timeout=5)
                create_booking(
                    master=self.master,
                    service=self.service,
                    target_date=self.monday,
                    start_time=time(9, 0),
                    client_name=name,
                    client_phone="0000000000",
                )
                results[name] = "success"
            except SlotUnavailableError:
                results[name] = "unavailable"
            finally:
                connection.close()

        thread_a = threading.Thread(target=attempt, args=("Клиент А",))
        thread_b = threading.Thread(target=attempt, args=("Клиент Б",))

        thread_a.start()
        thread_b.start()
        thread_a.join()
        thread_b.join()

        outcomes = sorted(results.values())
        self.assertEqual(outcomes, ["success", "unavailable"])
        self.assertEqual(Booking.objects.count(), 1)