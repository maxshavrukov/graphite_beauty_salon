from datetime import date, time, timedelta
from decimal import Decimal

from django.test import TestCase

from catalog.models import Absence, Booking, TimeBlock
from catalog.services import SlotUnavailableError, validate_booking_slot
from catalog.tests.factories import (
    make_absence,
    make_booking,
    make_master,
    make_master_service,
    make_service,
    make_work_day,
)


class ValidateBookingSlotTests(TestCase):
    def setUp(self):
        self.service = make_service()
        self.master = make_master()
        self.monday = date(2026, 9, 7)
        make_work_day(
            master=self.master,
            target_date=self.monday,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        self.master_service = make_master_service(
            self.master, self.service, price=Decimal("450.00"), duration=30,
        )

    def validate(self, start_time=time(9, 0), source: str = Booking.Source.ONLINE):
        return validate_booking_slot(
            self.master,
            self.service,
            self.monday,
            start_time,
            source,
        )

    def test_returns_master_service_for_free_slot(self):
        result = self.validate()

        self.assertEqual(result, self.master_service)
        self.assertEqual(result.price, Decimal("450.00"))
        self.assertEqual(result.duration, 30)

    def test_does_not_create_any_booking(self):
        self.validate()

        self.assertEqual(Booking.objects.count(), 0)

    def test_raises_when_master_is_inactive(self):
        self.master.is_active = False
        self.master.save()

        with self.assertRaises(SlotUnavailableError):
            self.validate()

    def test_raises_when_master_does_not_offer_service(self):
        other_service = make_service()

        with self.assertRaises(SlotUnavailableError):
            validate_booking_slot(
                self.master,
                other_service,
                self.monday,
                time(9, 0),
            )

    def test_raises_when_master_is_absent_even_for_admin(self):
        make_absence(self.master, self.monday)

        with self.assertRaises(SlotUnavailableError):
            self.validate(source=Booking.Source.ADMIN)

    def test_online_rejects_time_outside_working_hours(self):
        with self.assertRaises(SlotUnavailableError):
            self.validate(start_time=time(20, 0))

    def test_admin_allows_time_outside_working_hours(self):
        result = self.validate(
            start_time=time(20, 0),
            source=Booking.Source.ADMIN,
        )

        self.assertEqual(result, self.master_service)

    def test_admin_rejects_time_overlapping_active_booking(self):
        make_booking(
            master=self.master,
            service=self.service,
            target_date=self.monday,
            start_time=time(20, 0),
            duration=30,
        )

        with self.assertRaises(SlotUnavailableError):
            self.validate(
                start_time=time(20, 15),
                source=Booking.Source.ADMIN,
            )

    def test_cancelled_booking_does_not_block_time(self):
        make_booking(
            master=self.master,
            service=self.service,
            target_date=self.monday,
            start_time=time(20, 0),
            duration=30,
            status=Booking.Status.CANCELLED,
        )

        result = self.validate(
            start_time=time(20, 0),
            source=Booking.Source.ADMIN,
        )

        self.assertEqual(result, self.master_service)

    def test_phone_rejects_time_inside_time_block(self):
        TimeBlock.objects.create(
            master=self.master,
            date=self.monday,
            start_time=time(20, 0),
            end_time=time(21, 0),
            reason="Обед",
        )

        with self.assertRaises(SlotUnavailableError):
            self.validate(
                start_time=time(20, 0),
                source=Booking.Source.PHONE,
            )

    def test_raises_value_error_for_unknown_source(self):
        with self.assertRaises(ValueError):
            self.validate(source="UNKNOWN")

    def test_error_names_the_kind_of_absence(self):
        make_absence(self.master, self.monday, kind=Absence.Kind.SICK)

        with self.assertRaises(SlotUnavailableError) as context:
            self.validate(source=Booking.Source.ADMIN)

        self.assertIn("больничный", str(context.exception))

    def test_admin_allows_day_not_marked_as_working(self):
        unmarked_day = self.monday + timedelta(days=1)

        result = validate_booking_slot(
            self.master,
            self.service,
            unmarked_day,
            time(10, 0),
            Booking.Source.ADMIN,
        )

        self.assertEqual(result, self.master_service)
