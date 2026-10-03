from datetime import date, time, timedelta

from django.test import TestCase

from catalog.services import (
    get_candidate_starts,
    get_working_intervals,
    intervals_overlap,
)
from catalog.tests.factories import make_absence, make_master, make_work_day


class GetWorkingIntervalsTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.monday = date(2026, 9, 7)

    def test_returns_intervals_of_work_day(self):
        make_work_day(self.master, self.monday, time(9, 0), time(18, 0))

        result = get_working_intervals(self.master, self.monday)

        self.assertEqual(result, [(time(9, 0), time(18, 0))])

    def test_returns_two_intervals_for_day_with_break(self):
        make_work_day(
            self.master,
            self.monday,
            time(10, 0),
            time(19, 0),
            break_start=time(13, 0),
            break_end=time(14, 0),
        )

        result = get_working_intervals(self.master, self.monday)

        self.assertEqual(
            result,
            [(time(10, 0), time(13, 0)), (time(14, 0), time(19, 0))],
        )

    def test_returns_empty_when_day_is_not_marked(self):
        result = get_working_intervals(self.master, self.monday)

        self.assertEqual(result, [])

    def test_returns_empty_when_date_is_inside_absence(self):
        make_work_day(self.master, self.monday, time(9, 0), time(18, 0))
        make_absence(self.master, self.monday)

        result = get_working_intervals(self.master, self.monday)

        self.assertEqual(result, [])

    def test_absence_covers_both_boundary_dates(self):
        tuesday = self.monday + timedelta(days=1)
        make_work_day(self.master, self.monday)
        make_work_day(self.master, tuesday)
        make_absence(self.master, self.monday, tuesday)

        self.assertEqual(get_working_intervals(self.master, self.monday), [])
        self.assertEqual(get_working_intervals(self.master, tuesday), [])

    def test_absence_does_not_affect_dates_outside_its_range(self):
        make_work_day(self.master, self.monday, time(9, 0), time(18, 0))
        make_absence(self.master, self.monday + timedelta(days=1))

        result = get_working_intervals(self.master, self.monday)

        self.assertEqual(result, [(time(9, 0), time(18, 0))])

    def test_absence_of_other_master_does_not_affect(self):
        make_work_day(self.master, self.monday, time(9, 0), time(18, 0))
        make_absence(make_master(), self.monday)

        result = get_working_intervals(self.master, self.monday)

        self.assertEqual(result, [(time(9, 0), time(18, 0))])


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
