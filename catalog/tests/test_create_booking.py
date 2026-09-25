import threading
from datetime import date, time
from decimal import Decimal

from django.db import connection
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from catalog.models import Booking, ScheduleException, TimeBlock, WorkingHours
from catalog.services import SlotUnavailableError, create_booking, get_booking_end_time
from catalog.tests.factories import make_booking, make_master, make_master_service, make_service


class GetBookingEndTimeTests(TestCase):
    def test_computes_end_time_within_same_day(self):
        self.assertEqual(
            get_booking_end_time(time(9, 0), 30),
            time(9, 30),
        )

    def test_raises_when_service_crosses_midnight(self):
        with self.assertRaises(SlotUnavailableError):
            get_booking_end_time(time(23, 45), 30)

    def test_raises_when_service_ends_exactly_at_midnight(self):
        # 23:30 + 30 минут = 00:00 следующего дня — тоже "пересечение".
        with self.assertRaises(SlotUnavailableError):
            get_booking_end_time(time(23, 30), 30)


class CreateBookingTests(TestCase):
    def setUp(self):
        self.service = make_service()
        self.master = make_master()
        self.monday = date(2026, 9, 7)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

    def test_creates_booking_with_snapshotted_price_and_duration(self):
        make_master_service(self.master, self.service, price=Decimal("450.00"), duration=30)

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
        master_service = make_master_service(
            self.master, self.service, price=Decimal("450.00"), duration=30,
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
        make_master_service(self.master, self.service, duration=30)

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
        self.assertEqual(booking.comment, "Записал администратор по телефону")

    def test_raises_for_invalid_source(self):
        make_master_service(self.master, self.service, duration=30)

        with self.assertRaises(ValueError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(9, 0),
                client_name="Иван",
                client_phone="+380000000000",
                source="TELEGRAM",
            )

    def test_raises_when_master_is_inactive(self):
        make_master_service(self.master, self.service, duration=30)
        self.master.is_active = False
        self.master.save()

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

    def test_raises_when_master_does_not_offer_service(self):
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
        make_master_service(self.master, self.service, duration=30, is_active=False)

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
        make_master_service(self.master, self.service, duration=30)
        ScheduleException.objects.create(
            master=self.master, date=self.monday, is_closed=True,
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

    def test_closed_day_blocks_admin_source_too(self):
        # Закрытый день нельзя обойти даже административной записью.
        make_master_service(self.master, self.service, duration=30)
        ScheduleException.objects.create(
            master=self.master, date=self.monday, is_closed=True,
        )

        with self.assertRaises(SlotUnavailableError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(9, 0),
                client_name="Иван",
                client_phone="+380000000000",
                source=Booking.Source.ADMIN,
            )

    def test_raises_when_slot_already_taken_and_does_not_duplicate(self):
        make_master_service(self.master, self.service, duration=30)
        make_booking(
            master=self.master,
            service=self.service,
            target_date=self.monday,
            start_time=time(9, 0),
            duration=30,
            client_name="Первый клиент",
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
        self.assertEqual(Booking.objects.get().client_name, "Первый клиент")


class CreateBookingPhoneAndAdminTests(TestCase):
    """
    PHONE/ADMIN может работать вне обычного расписания — но всё
    равно должен уважать блокировки времени и уже существующие
    записи (в отличие от ONLINE, который вообще не может выйти
    за пределы WorkingHours).
    """

    def setUp(self):
        self.service = make_service()
        self.master = make_master()
        self.monday = date(2026, 9, 7)
        make_master_service(self.master, self.service, duration=30)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

    def test_online_cannot_book_outside_working_hours(self):
        with self.assertRaises(SlotUnavailableError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(20, 0),
                client_name="Иван",
                client_phone="+380000000000",
                source=Booking.Source.ONLINE,
            )

    def test_phone_can_book_outside_working_hours(self):
        booking = create_booking(
            master=self.master,
            service=self.service,
            target_date=self.monday,
            start_time=time(20, 0),
            client_name="Иван",
            client_phone="+380000000000",
            source=Booking.Source.PHONE,
        )

        self.assertEqual(booking.start_time, time(20, 0))
        self.assertEqual(booking.source, Booking.Source.PHONE)

    def test_admin_can_book_outside_working_hours(self):
        booking = create_booking(
            master=self.master,
            service=self.service,
            target_date=self.monday,
            start_time=time(20, 0),
            client_name="Иван",
            client_phone="+380000000000",
            source=Booking.Source.ADMIN,
        )

        self.assertEqual(booking.source, Booking.Source.ADMIN)

    def test_phone_still_blocked_by_time_block(self):
        TimeBlock.objects.create(
            master=self.master,
            date=self.monday,
            start_time=time(20, 0),
            end_time=time(20, 30),
            reason="Личные дела",
        )

        with self.assertRaises(SlotUnavailableError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(20, 0),
                client_name="Иван",
                client_phone="+380000000000",
                source=Booking.Source.PHONE,
            )

    def test_phone_still_blocked_by_existing_booking(self):
        make_booking(
            master=self.master,
            service=self.service,
            target_date=self.monday,
            start_time=time(20, 0),
            duration=30,
        )

        with self.assertRaises(SlotUnavailableError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(20, 0),
                client_name="Иван",
                client_phone="+380000000000",
                source=Booking.Source.PHONE,
            )

    def test_phone_crossing_midnight_is_rejected(self):
        with self.assertRaises(SlotUnavailableError):
            create_booking(
                master=self.master,
                service=self.service,
                target_date=self.monday,
                start_time=time(23, 45),
                client_name="Иван",
                client_phone="+380000000000",
                source=Booking.Source.PHONE,
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
        self.service = make_service()
        self.master = make_master()
        make_master_service(self.master, self.service, duration=30)
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
