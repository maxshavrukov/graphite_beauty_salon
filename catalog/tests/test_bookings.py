from datetime import date, time

from django.test import TestCase

from catalog.models import Booking
from catalog.services import filter_candidates_by_bookings, get_active_bookings
from catalog.tests.factories import make_booking, make_master, make_service


class FilterCandidatesByBookingsTests(TestCase):
    def test_active_statuses_block_overlapping_candidate(self):
        # NEW и CONFIRMED должны блокировать время одинаково.
        for status in (Booking.Status.NEW, Booking.Status.CONFIRMED):
            with self.subTest(status=status):
                booking = make_booking(
                    target_date=date(2026, 9, 7),
                    start_time=time(10, 15),
                    duration=30,
                    status=status,
                )

                result = filter_candidates_by_bookings(
                    [time(10, 0)],
                    [booking],
                    service_duration_minutes=30,
                )

                self.assertEqual(result, [])

    def test_booking_touching_candidate_boundary_does_not_block(self):
        booking = make_booking(
            target_date=date(2026, 9, 7),
            start_time=time(10, 0),
            duration=30,
        )

        result = filter_candidates_by_bookings(
            [time(10, 30)],
            [booking],
            service_duration_minutes=30,
        )

        self.assertEqual(result, [time(10, 30)])

    def test_booking_duration_blocks_later_candidate(self):
        booking = make_booking(
            target_date=date(2026, 9, 7),
            start_time=time(10, 0),
            duration=60,
        )

        result = filter_candidates_by_bookings(
            [time(10, 45)],
            [booking],
            service_duration_minutes=30,
        )

        self.assertEqual(result, [])

    def test_get_active_bookings_returns_only_new_and_confirmed(self):
        master = make_master()
        service = make_service()

        for status, start_time in [
            (Booking.Status.NEW, time(10, 0)),
            (Booking.Status.CONFIRMED, time(11, 0)),
            (Booking.Status.CANCELLED, time(12, 0)),
            (Booking.Status.COMPLETED, time(13, 0)),
        ]:
            make_booking(
                master=master,
                service=service,
                target_date=date(2026, 9, 7),
                start_time=start_time,
                status=status,
            )

        result = get_active_bookings(master, date(2026, 9, 7))

        self.assertEqual(
            list(result.values_list("status", flat=True)),
            [Booking.Status.NEW, Booking.Status.CONFIRMED],
        )

    def test_get_active_bookings_filters_by_master_and_date(self):
        master = make_master()
        another_master = make_master()

        make_booking(
            master=master,
            target_date=date(2026, 9, 7),
            start_time=time(10, 0),
            client_name="Нужная запись",
        )
        make_booking(
            master=another_master,
            target_date=date(2026, 9, 7),
            start_time=time(11, 0),
            client_name="Другой мастер",
        )
        make_booking(
            master=master,
            target_date=date(2026, 9, 8),
            start_time=time(12, 0),
            client_name="Другая дата",
        )

        result = get_active_bookings(master, date(2026, 9, 7))

        self.assertEqual(result.count(), 1)
        self.assertEqual(result[0].client_name, "Нужная запись")
