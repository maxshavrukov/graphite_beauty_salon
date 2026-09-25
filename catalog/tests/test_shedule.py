from datetime import date, time

from django.test import TestCase

from catalog.models import ScheduleException, WorkingHours
from catalog.services import (
    get_candidate_starts,
    get_working_intervals,
    intervals_overlap,
)
from catalog.tests.factories import make_master


class GetWorkingIntervalsTests(TestCase):
    def test_returns_working_hours_for_weekday(self):
        master = make_master()
        WorkingHours.objects.create(
            master=master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        result = get_working_intervals(master, date(2026, 9, 7))

        self.assertEqual(result, [(time(9, 0), time(18, 0))])

    def test_returns_multiple_working_intervals_for_weekday(self):
        master = make_master()
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

        result = get_working_intervals(master, date(2026, 9, 7))

        self.assertEqual(
            result,
            [(time(10, 0), time(13, 0)), (time(14, 0), time(19, 0))],
        )

    def test_returns_empty_for_closed_schedule_exception(self):
        master = make_master()
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

        result = get_working_intervals(master, date(2026, 9, 7))

        self.assertEqual(result, [])

    def test_exception_overrides_working_hours(self):
        master = make_master()
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

        result = get_working_intervals(master, date(2026, 9, 7))

        self.assertEqual(result, [(time(11, 0), time(16, 0))])


class GetCandidateStartsTests(TestCase):
    def test_generates_15_minute_candidates(self):
        result = get_candidate_starts(
            [(time(9, 0), time(10, 0))],
            duration_minutes=30,
        )

        self.assertEqual(result, [time(9, 0), time(9, 15), time(9, 30)])

    def test_generates_one_candidate_when_duration_fills_interval(self):
        result = get_candidate_starts(
            [(time(9, 0), time(10, 0))],
            duration_minutes=60,
        )

        self.assertEqual(result, [time(9, 0)])

    def test_generates_candidates_for_multiple_working_intervals(self):
        result = get_candidate_starts(
            [(time(10, 0), time(11, 0)), (time(14, 0), time(14, 30))],
            duration_minutes=30,
        )

        # По одному кандидату на каждый интервал: услуга (30 мин)
        # с шагом 15 мин помещается в 10:00-11:00 только с 10:00
        # (10:15+30 уже вышло бы за 11:00... проверим оба интервала
        # отдельно, не разворачивая полный список вручную).
        self.assertIn(time(10, 0), result)
        self.assertIn(time(14, 0), result)
        self.assertNotIn(time(14, 15), result)


class IntervalsOverlapTests(TestCase):
    def test_returns_true_when_intervals_overlap(self):
        result = intervals_overlap(
            time(10, 0), time(11, 0), time(10, 30), time(11, 30),
        )
        self.assertTrue(result)

    def test_returns_false_when_intervals_only_touch(self):
        result = intervals_overlap(
            time(10, 0), time(11, 0), time(11, 0), time(12, 0),
        )
        self.assertFalse(result)

    def test_returns_false_when_intervals_do_not_overlap(self):
        result = intervals_overlap(
            time(10, 0), time(11, 0), time(12, 0), time(13, 0),
        )
        self.assertFalse(result)
