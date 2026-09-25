from datetime import date, time

from django.test import TestCase

from catalog.models import ScheduleException, TimeBlock, WorkingHours
from catalog.services import get_available_slots
from catalog.tests.factories import make_booking, make_master, make_master_service, make_service


class GetAvailableSlotsTests(TestCase):
    def setUp(self):
        self.service = make_service()
        self.master = make_master()
        self.target_date = date(2026, 9, 7)  # понедельник

    def test_returns_all_candidates_when_day_is_free(self):
        make_master_service(self.master, self.service, duration=30)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [time(9, 0), time(9, 15), time(9, 30)])

    def test_returns_empty_when_master_does_not_provide_service(self):
        # MasterService специально не создаём.
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [])

    def test_returns_empty_when_master_service_is_inactive(self):
        make_master_service(self.master, self.service, duration=30, is_active=False)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [])

    def test_returns_empty_when_day_off(self):
        make_master_service(self.master, self.service, duration=30)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        ScheduleException.objects.create(
            master=self.master, date=self.target_date, is_closed=True,
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [])

    def test_schedule_exception_overrides_working_hours(self):
        make_master_service(self.master, self.service, duration=30)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        ScheduleException.objects.create(
            master=self.master,
            date=self.target_date,
            is_closed=False,
            start_time=time(12, 0),
            end_time=time(13, 0),
        )

        result = get_available_slots(
            self.master, self.service, self.target_date, slot_step_minutes=30,
        )

        self.assertEqual(result, [time(12, 0), time(12, 30)])

    def test_time_block_removes_overlapping_slot(self):
        make_master_service(self.master, self.service, duration=30)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        TimeBlock.objects.create(
            master=self.master,
            date=self.target_date,
            start_time=time(9, 0),
            end_time=time(9, 30),
            reason="Личные дела",
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [time(9, 30)])

    def test_active_booking_removes_overlapping_slot(self):
        make_master_service(self.master, self.service, duration=30)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        make_booking(
            master=self.master,
            service=self.service,
            target_date=self.target_date,
            start_time=time(9, 0),
            duration=30,
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [time(9, 30)])

    def test_cancelled_booking_does_not_remove_slot(self):
        make_master_service(self.master, self.service, duration=30)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(9, 30),
        )
        make_booking(
            master=self.master,
            service=self.service,
            target_date=self.target_date,
            start_time=time(9, 0),
            duration=30,
            status="CANCELLED",
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [time(9, 0)])

    def test_uses_master_service_duration_not_arbitrary_value(self):
        make_master_service(self.master, self.service, duration=60)
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        # При длительности услуги 60 минут в окне 9:00-10:00
        # помещается только один кандидат: 9:00.
        self.assertEqual(result, [time(9, 0)])
