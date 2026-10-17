"""
Страж статусов записи.

Какие статусы занимают время мастера, решено в одном месте —
Booking.ACTIVE_STATUSES. Эти тесты проверяют, что все части проекта
(расчёт слотов, редактор расписания, календарь, форма в админке)
согласны между собой, и не дают добавить новый статус «молча».
"""

from datetime import date, time

from django.test import TestCase

from catalog.admin import BookingChangeForm
from catalog.models import Booking
from catalog.services import (
    find_active_bookings,
    get_active_bookings,
    get_month_calendar,
)
from catalog.tests.factories import make_booking, make_master, make_service

MONDAY = date(2026, 10, 5)

# Решение о каждом статусе принято здесь явно. Появится новый статус —
# test_every_status_is_classified упадёт и заставит решить, занимает ли он
# время мастера (и обновить Booking.ACTIVE_STATUSES при необходимости).
ACTIVE = {Booking.Status.NEW, Booking.Status.CONFIRMED}
CLOSED = {
    Booking.Status.CANCELLED,
    Booking.Status.COMPLETED,
    Booking.Status.NO_SHOW,
}


class BookingStatusAgreementTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.service = make_service()
        self.by_status = {}

        for hour, status in zip(range(9, 9 + len(Booking.Status)), Booking.Status):
            self.by_status[status] = make_booking(
                master=self.master,
                service=self.service,
                target_date=MONDAY,
                start_time=time(hour, 0),
                status=status,
            )

    def test_every_status_is_classified(self):
        self.assertEqual(set(Booking.Status), ACTIVE | CLOSED)

    def test_active_statuses_constant_matches_the_decision(self):
        self.assertEqual(set(Booking.ACTIVE_STATUSES), ACTIVE)

    def test_slot_calculation_blocks_exactly_active_statuses(self):
        blocking = {booking.status for booking in get_active_bookings(self.master, MONDAY)}

        self.assertEqual(blocking, ACTIVE)

    def test_schedule_editor_finds_exactly_active_bookings(self):
        found = {booking.status for booking in find_active_bookings(self.master, [MONDAY])}

        self.assertEqual(found, ACTIVE)

    def test_month_calendar_counts_exactly_active_bookings(self):
        days = get_month_calendar(self.master, 2026, 10, today=date(2026, 10, 1))

        self.assertEqual(days[MONDAY.day - 1].bookings_count, len(ACTIVE))

    def test_no_closed_status_can_be_returned_to_work_in_admin(self):
        for status in CLOSED:
            with self.subTest(status=status):
                booking = self.by_status[status]
                form = BookingChangeForm(
                    data={
                        "client_name": booking.client_name,
                        "client_phone": booking.client_phone,
                        "status": Booking.Status.NEW,
                        "comment": "",
                    },
                    instance=booking,
                )

                self.assertFalse(form.is_valid())
                self.assertIn("status", form.errors)
