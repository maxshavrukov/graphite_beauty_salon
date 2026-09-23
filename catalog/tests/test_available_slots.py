from datetime import date, time

from django.test import TestCase

from catalog.models import (
    Booking,
    Master,
    MasterService,
    Service,
    ServiceCategory,
    ScheduleException,
    TimeBlock,
    WorkingHours,
)
from catalog.services import get_available_slots


class GetAvailableSlotsTests(TestCase):
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
        self.target_date = date(2026, 9, 7)  # понедельник

    def test_returns_all_candidates_when_day_is_free(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=1000,
            duration=30,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        result = get_available_slots(
            self.master,
            self.service,
            self.target_date,
            slot_step_minutes=15,
        )

        self.assertEqual(
            result,
            [time(9, 0), time(9, 15), time(9, 30)],
        )

    def test_returns_empty_when_master_does_not_provide_service(self):
        # MasterService специально не создаём.
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        result = get_available_slots(
            self.master,
            self.service,
            self.target_date,
        )

        self.assertEqual(result, [])

    def test_returns_empty_when_master_service_is_inactive(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=1000,
            duration=30,
            is_active=False,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        result = get_available_slots(
            self.master,
            self.service,
            self.target_date,
        )

        self.assertEqual(result, [])

    def test_returns_empty_when_day_off(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=1000,
            duration=30,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        ScheduleException.objects.create(
            master=self.master,
            date=self.target_date,
            is_closed=True,
        )

        result = get_available_slots(
            self.master,
            self.service,
            self.target_date,
        )

        self.assertEqual(result, [])

    def test_schedule_exception_overrides_working_hours(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=1000,
            duration=30,
        )
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
            self.master,
            self.service,
            self.target_date,
            slot_step_minutes=30,
        )

        self.assertEqual(result, [time(12, 0), time(12, 30)])

    def test_time_block_removes_overlapping_slot(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=1000,
            duration=30,
        )
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

        result = get_available_slots(
            self.master,
            self.service,
            self.target_date,
            slot_step_minutes=15,
        )

        self.assertEqual(result, [time(9, 30)])

    def test_active_booking_removes_overlapping_slot(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=1000,
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
            date=self.target_date,
            start_time=time(9, 0),
            client_name="Занявший клиент",
            client_phone="0000000000",
            price=1000,
            duration=30,
            status=Booking.Status.NEW,
            source=Booking.Source.ONLINE,
        )

        result = get_available_slots(
            self.master,
            self.service,
            self.target_date,
            slot_step_minutes=15,
        )

        self.assertEqual(result, [time(9, 30)])

    def test_cancelled_booking_does_not_remove_slot(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=1000,
            duration=30,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(9, 30),
        )
        Booking.objects.create(
            master=self.master,
            service=self.service,
            date=self.target_date,
            start_time=time(9, 0),
            client_name="Отменивший клиент",
            client_phone="0000000000",
            price=1000,
            duration=30,
            status=Booking.Status.CANCELLED,
            source=Booking.Source.ONLINE,
        )

        result = get_available_slots(
            self.master,
            self.service,
            self.target_date,
        )

        self.assertEqual(result, [time(9, 0)])

    def test_uses_master_service_duration_not_arbitrary_value(self):
        MasterService.objects.create(
            master=self.master,
            service=self.service,
            price=1000,
            duration=60,
        )
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        result = get_available_slots(
            self.master,
            self.service,
            self.target_date,
            slot_step_minutes=15,
        )

        # При длительности услуги 60 минут в окне 9:00-10:00
        # помещается только один кандидат: 9:00.
        self.assertEqual(result, [time(9, 0)])