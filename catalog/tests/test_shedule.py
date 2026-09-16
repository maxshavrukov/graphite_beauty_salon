from datetime import date, time
from django.test import TestCase
from catalog.models import Master, ScheduleException, WorkingHours
from catalog.services import (
    get_candidate_starts,
    get_working_intervals,
    intervals_overlap,
)


class GetWorkingIntervalsTests(TestCase):

    def test_returns_working_hours_for_weekday(self):
        master = Master.objects.create(
            name="Тестовый мастер",
            slug="test-master",
        )

        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        result = get_working_intervals(
            master,
            date(2026, 9, 7),
        )

        self.assertEqual(
            result,
            [
                (time(9, 0), time(18, 0)),
            ],
        )

    def test_returns_multiple_working_intervals_for_weekday(self):
        master = Master.objects.create(
            name="Мастер с перерывом",
            slug="master-with-break",
        )

        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(10, 0),
            end_time=time(13, 0),
        )

        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(14, 0),
            end_time=time(19, 0),
        )

        result = get_working_intervals(
            master,
            date(2026, 9, 7),
        )

        self.assertEqual(
            result,
            [
                (time(10, 0), time(13, 0)),
                (time(14, 0), time(19, 0)),
            ],
        )

    def test_returns_empty_for_closed_schedule_exception(self):
        master = Master.objects.create(
            name="Мастер с выходным",
            slug="master-with-day-off",
        )

        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        ScheduleException.objects.create(
            master=master,
            date=date(2026, 9, 7),
            is_closed=True,
        )

        result = get_working_intervals(
            master,
            date(2026, 9, 7),
        )

        self.assertEqual(result, [])

    def test_exception_overrides_working_hours(self):
        master = Master.objects.create(
            name="Мастер с изменённым графиком",
            slug="master-with-exception",
        )

        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        ScheduleException.objects.create(
            master=master,
            date=date(2026, 9, 7),
            is_closed=False,
            start_time=time(11, 0),
            end_time=time(16, 0),
        )

        result = get_working_intervals(
            master,
            date(2026, 9, 7),
        )

        self.assertEqual(
            result,
            [
                (time(11, 0), time(16, 0)),
            ],
        )


class GetCandidateStartsTests(TestCase):

    def test_generates_15_minute_candidates(self):
        working_intervals = [
            (time(9, 0), time(10, 0)),
        ]

        result = get_candidate_starts(
            working_intervals,
            duration_minutes=30,
        )

        self.assertEqual(
            result,
            [
                time(9, 0),
                time(9, 15),
                time(9, 30),
            ],
        )

    def test_generates_one_candidate_when_duration_fills_interval(self):
        working_intervals = [
            (time(9, 0), time(10, 0)),
        ]

        result = get_candidate_starts(
            working_intervals,
            duration_minutes=60,
        )

        self.assertEqual(
            result,
            [
                time(9, 0),
            ],
        )

    def test_generates_candidates_for_multiple_working_intervals(self):
        working_intervals = [
            (time(10, 0), time(13, 0)),
            (time(14, 0), time(19, 0)),
        ]

        result = get_candidate_starts(
            working_intervals,
            duration_minutes=30,
        )

        self.assertEqual(
            result,
            [
                time(10, 0),
                time(10, 15),
                time(10, 30),
                time(10, 45),
                time(11, 0),
                time(11, 15),
                time(11, 30),
                time(11, 45),
                time(12, 0),
                time(12, 15),
                time(12, 30),
                time(14, 0),
                time(14, 15),
                time(14, 30),
                time(14, 45),
                time(15, 0),
                time(15, 15),
                time(15, 30),
                time(15, 45),
                time(16, 0),
                time(16, 15),
                time(16, 30),
                time(16, 45),
                time(17, 0),
                time(17, 15),
                time(17, 30),
                time(17, 45),
                time(18, 0),
                time(18, 15),
                time(18, 30),
            ],
        )


class IntervalsOverlapTests(TestCase):

    def test_returns_true_when_intervals_overlap(self):
        result = intervals_overlap(
            time(10, 0),
            time(11, 0),
            time(10, 30),
            time(11, 30),
        )

        self.assertTrue(result)

    def test_returns_false_when_intervals_only_touch(self):
        result = intervals_overlap(
            time(10, 0),
            time(11, 0),
            time(11, 0),
            time(12, 0),
        )

        self.assertFalse(result)

    def test_returns_false_when_intervals_do_not_overlap(self):
        result = intervals_overlap(
            time(10, 0),
            time(11, 0),
            time(12, 0),
            time(13, 0),
        )

        self.assertFalse(result)