from datetime import date, time, timedelta

from django.test import TestCase
from django.utils import timezone

from catalog.models import Booking, TimeBlock
from catalog.services import get_available_slots
from catalog.tests.factories import (
    make_absence,
    make_booking,
    make_master,
    make_master_service,
    make_service,
    make_work_day,
)


class GetAvailableSlotsTests(TestCase):
    def setUp(self):
        self.service = make_service()
        self.master = make_master()
        self.target_date = date(2026, 9, 7)  # понедельник

    def test_returns_all_candidates_when_day_is_free(self):
        make_master_service(self.master, self.service, duration=30)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [time(9, 0), time(9, 15), time(9, 30)])

    def test_returns_empty_when_master_does_not_provide_service(self):
        # MasterService специально не создаём.
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [])

    def test_returns_empty_when_master_service_is_inactive(self):
        make_master_service(self.master, self.service, duration=30, is_active=False)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [])

    def test_returns_empty_when_master_is_absent(self):
        make_master_service(self.master, self.service, duration=30)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        make_absence(self.master, self.target_date)

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [])

    def test_break_inside_work_day_removes_slots_during_break(self):
        make_master_service(self.master, self.service, duration=30)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(11, 0),
            break_start=time(10, 0),
            break_end=time(10, 30),
        )

        result = get_available_slots(
            self.master, self.service, self.target_date, slot_step_minutes=30,
        )

        # Перерыв 10:00–10:30 вырезан из дня: остаются 9:00, 9:30 и 10:30.
        self.assertEqual(result, [time(9, 0), time(9, 30), time(10, 30)])

    def test_returns_empty_when_day_is_not_marked(self):
        make_master_service(self.master, self.service, duration=30)
        # Рабочий день не создан: мастер в эту дату не отмечен.

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [])

    def test_absence_does_not_affect_other_dates(self):
        make_master_service(self.master, self.service, duration=30)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(9, 30),
        )
        make_absence(self.master, self.target_date + timedelta(days=1))

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [time(9, 0)])

    def test_time_block_removes_overlapping_slot(self):
        make_master_service(self.master, self.service, duration=30)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
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
        make_work_day(
            master=self.master,
            target_date=self.target_date,
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
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(9, 30),
        )
        make_booking(
            master=self.master,
            service=self.service,
            target_date=self.target_date,
            start_time=time(9, 0),
            duration=30,
            status=Booking.Status.CANCELLED,
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        self.assertEqual(result, [time(9, 0)])

    def test_uses_master_service_duration_not_arbitrary_value(self):
        make_master_service(self.master, self.service, duration=60)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        result = get_available_slots(self.master, self.service, self.target_date)

        # При длительности услуги 60 минут в окне 9:00-10:00
        # помещается только один кандидат: 9:00.
        self.assertEqual(result, [time(9, 0)])

    def test_excludes_times_within_lead_time_when_date_is_today(self):
        make_master_service(self.master, self.service, duration=30)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(12, 0),
        )
        # Отступ по умолчанию — 60 минут (BOOKING_MIN_LEAD_MINUTES).
        now = timezone.make_aware(
            timezone.datetime.combine(self.target_date, time(10, 5)),
        )

        result = get_available_slots(
            self.master, self.service, self.target_date, now=now,
        )

        # Меньше часа до начала — не бронируется, даже 10:15 и 11:00.
        self.assertNotIn(time(10, 15), result)
        self.assertNotIn(time(11, 0), result)
        # Ровно 60 минут — можно; ближайший слот на сетке 15 минут
        # после отсечки 11:05 — это 11:15.
        self.assertIn(time(11, 15), result)

    def test_returns_empty_for_today_when_lead_time_crosses_midnight(self):
        make_master_service(self.master, self.service, duration=30)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(23, 0),
            end_time=time(23, 45),
        )
        # 23:30 + 60 минут = 00:30 следующего дня — на сегодня
        # бронировать больше нечего, каким бы ни было расписание.
        now = timezone.make_aware(
            timezone.datetime.combine(self.target_date, time(23, 30)),
        )

        result = get_available_slots(
            self.master, self.service, self.target_date, now=now,
        )

        self.assertEqual(result, [])

    def test_does_not_exclude_past_looking_times_on_future_dates(self):
        # "Сейчас 10:05" не должно резать слоты 9:00 на дату,
        # которая ещё не наступила.
        make_master_service(self.master, self.service, duration=30)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        earlier_moment = timezone.make_aware(
            timezone.datetime.combine(
                self.target_date - timedelta(days=1),
                time(10, 5),
            ),
        )

        result = get_available_slots(
            self.master, self.service, self.target_date, now=earlier_moment,
        )

        self.assertEqual(result, [time(9, 0), time(9, 15), time(9, 30)])
