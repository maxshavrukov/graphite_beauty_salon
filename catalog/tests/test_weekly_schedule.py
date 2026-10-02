from datetime import time

from django.test import SimpleTestCase, TestCase

from catalog.models import Master, WorkingHours
from catalog.services.weekly_schedule import (
    DaySchedule,
    day_to_intervals,
    get_day_error,
    get_weekly_schedule,
    intervals_to_day,
    save_weekly_schedule,
)
from catalog.tests.factories import make_master

MONDAY = WorkingHours.Weekday.MONDAY
TUESDAY = WorkingHours.Weekday.TUESDAY
SATURDAY = WorkingHours.Weekday.SATURDAY


# ---------------------------------------------------------------------------
# Чистая логика: без базы данных
# ---------------------------------------------------------------------------


class GetDayErrorTests(SimpleTestCase):
    def test_day_off_is_always_valid(self):
        self.assertIsNone(get_day_error(DaySchedule(works=False)))

    def test_valid_day_without_break(self):
        day = DaySchedule(works=True, start=time(9, 0), end=time(18, 0))

        self.assertIsNone(get_day_error(day))

    def test_valid_day_with_break(self):
        day = DaySchedule(
            works=True,
            start=time(9, 0),
            end=time(18, 0),
            break_start=time(13, 0),
            break_end=time(14, 0),
        )

        self.assertIsNone(get_day_error(day))

    def test_error_when_working_day_has_no_times(self):
        self.assertIsNotNone(get_day_error(DaySchedule(works=True)))

    def test_error_when_end_not_after_start(self):
        day = DaySchedule(works=True, start=time(18, 0), end=time(9, 0))

        self.assertIsNotNone(get_day_error(day))

    def test_error_when_only_one_side_of_break_given(self):
        day = DaySchedule(
            works=True,
            start=time(9, 0),
            end=time(18, 0),
            break_start=time(13, 0),
        )

        self.assertIsNotNone(get_day_error(day))

    def test_error_when_break_end_not_after_break_start(self):
        day = DaySchedule(
            works=True,
            start=time(9, 0),
            end=time(18, 0),
            break_start=time(14, 0),
            break_end=time(13, 0),
        )

        self.assertIsNotNone(get_day_error(day))

    def test_error_when_break_is_outside_working_time(self):
        day = DaySchedule(
            works=True,
            start=time(9, 0),
            end=time(18, 0),
            break_start=time(17, 0),
            break_end=time(19, 0),
        )

        self.assertIsNotNone(get_day_error(day))


class DayToIntervalsTests(SimpleTestCase):
    def test_day_off_gives_no_intervals(self):
        self.assertEqual(day_to_intervals(DaySchedule(works=False)), [])

    def test_ignores_times_of_day_off(self):
        day = DaySchedule(works=False, start=time(9, 0), end=time(18, 0))

        self.assertEqual(day_to_intervals(day), [])

    def test_day_without_break_gives_one_interval(self):
        day = DaySchedule(works=True, start=time(9, 0), end=time(18, 0))

        self.assertEqual(
            day_to_intervals(day),
            [(time(9, 0), time(18, 0))],
        )

    def test_day_with_break_gives_two_intervals(self):
        day = DaySchedule(
            works=True,
            start=time(9, 0),
            end=time(18, 0),
            break_start=time(13, 0),
            break_end=time(14, 0),
        )

        self.assertEqual(
            day_to_intervals(day),
            [
                (time(9, 0), time(13, 0)),
                (time(14, 0), time(18, 0)),
            ],
        )

    def test_raises_value_error_for_invalid_day(self):
        day = DaySchedule(works=True, start=time(18, 0), end=time(9, 0))

        with self.assertRaises(ValueError):
            day_to_intervals(day)


class IntervalsToDayTests(SimpleTestCase):
    def test_no_intervals_is_day_off(self):
        self.assertEqual(intervals_to_day([]), DaySchedule(works=False))

    def test_one_interval_has_no_break(self):
        day = intervals_to_day([(time(9, 0), time(18, 0))])

        self.assertEqual(
            day,
            DaySchedule(works=True, start=time(9, 0), end=time(18, 0)),
        )

    def test_two_intervals_become_break(self):
        day = intervals_to_day(
            [
                (time(9, 0), time(13, 0)),
                (time(14, 0), time(18, 0)),
            ]
        )

        self.assertEqual(
            day,
            DaySchedule(
                works=True,
                start=time(9, 0),
                end=time(18, 0),
                break_start=time(13, 0),
                break_end=time(14, 0),
            ),
        )

    def test_order_of_intervals_does_not_matter(self):
        day = intervals_to_day(
            [
                (time(14, 0), time(18, 0)),
                (time(9, 0), time(13, 0)),
            ]
        )

        self.assertEqual(day.start, time(9, 0))
        self.assertEqual(day.break_start, time(13, 0))

    def test_touching_intervals_are_one_continuous_day(self):
        day = intervals_to_day(
            [
                (time(9, 0), time(13, 0)),
                (time(13, 0), time(18, 0)),
            ]
        )

        self.assertEqual(
            day,
            DaySchedule(works=True, start=time(9, 0), end=time(18, 0)),
        )

    def test_three_intervals_show_only_first_break(self):
        day = intervals_to_day(
            [
                (time(9, 0), time(11, 0)),
                (time(12, 0), time(15, 0)),
                (time(16, 0), time(18, 0)),
            ]
        )

        self.assertEqual(day.start, time(9, 0))
        self.assertEqual(day.end, time(18, 0))
        self.assertEqual(day.break_start, time(11, 0))
        self.assertEqual(day.break_end, time(12, 0))

    def test_round_trip_keeps_intervals(self):
        intervals = [
            (time(9, 0), time(13, 0)),
            (time(14, 0), time(18, 0)),
        ]

        self.assertEqual(
            day_to_intervals(intervals_to_day(intervals)),
            intervals,
        )


# ---------------------------------------------------------------------------
# Работа с базой данных
# ---------------------------------------------------------------------------


def _hours(master, weekday):
    return list(
        WorkingHours.objects.filter(master=master, weekday=weekday)
        .order_by("start_time")
        .values_list("start_time", "end_time")
    )


class GetWeeklyScheduleTests(TestCase):
    def setUp(self):
        self.master = make_master()

    def test_returns_all_seven_days_as_off_when_no_hours(self):
        week = get_weekly_schedule(self.master)

        self.assertEqual(sorted(week), [0, 1, 2, 3, 4, 5, 6])
        self.assertTrue(all(not day.works for day in week.values()))

    def test_reads_single_interval(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        week = get_weekly_schedule(self.master)

        self.assertEqual(
            week[MONDAY],
            DaySchedule(works=True, start=time(9, 0), end=time(18, 0)),
        )
        self.assertFalse(week[TUESDAY].works)

    def test_reads_two_intervals_as_break(self):
        for start, end in [(time(9, 0), time(13, 0)), (time(14, 0), time(18, 0))]:
            WorkingHours.objects.create(
                master=self.master,
                weekday=MONDAY,
                start_time=start,
                end_time=end,
            )

        day = get_weekly_schedule(self.master)[MONDAY]

        self.assertEqual(day.break_start, time(13, 0))
        self.assertEqual(day.break_end, time(14, 0))

    def test_unsaved_master_gets_empty_week(self):
        master = Master(name="Новый", slug="new-master")

        week = get_weekly_schedule(master)

        self.assertEqual(len(week), 7)
        self.assertTrue(all(not day.works for day in week.values()))


class SaveWeeklyScheduleTests(TestCase):
    def setUp(self):
        self.master = make_master()

    def test_creates_interval_for_working_day(self):
        save_weekly_schedule(
            self.master,
            {MONDAY: DaySchedule(works=True, start=time(9, 0), end=time(18, 0))},
        )

        self.assertEqual(
            _hours(self.master, MONDAY),
            [(time(9, 0), time(18, 0))],
        )

    def test_saves_break_as_two_intervals(self):
        save_weekly_schedule(
            self.master,
            {
                MONDAY: DaySchedule(
                    works=True,
                    start=time(9, 0),
                    end=time(18, 0),
                    break_start=time(13, 0),
                    break_end=time(14, 0),
                )
            },
        )

        self.assertEqual(
            _hours(self.master, MONDAY),
            [
                (time(9, 0), time(13, 0)),
                (time(14, 0), time(18, 0)),
            ],
        )

    def test_replaces_existing_intervals(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        save_weekly_schedule(
            self.master,
            {MONDAY: DaySchedule(works=True, start=time(10, 0), end=time(16, 0))},
        )

        self.assertEqual(
            _hours(self.master, MONDAY),
            [(time(10, 0), time(16, 0))],
        )

    def test_day_off_removes_existing_intervals(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=SATURDAY,
            start_time=time(10, 0),
            end_time=time(15, 0),
        )

        save_weekly_schedule(self.master, {SATURDAY: DaySchedule(works=False)})

        self.assertEqual(_hours(self.master, SATURDAY), [])

    def test_leaves_days_not_in_week_untouched(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=TUESDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        save_weekly_schedule(
            self.master,
            {MONDAY: DaySchedule(works=True, start=time(9, 0), end=time(18, 0))},
        )

        self.assertEqual(
            _hours(self.master, TUESDAY),
            [(time(9, 0), time(18, 0))],
        )

    def test_leaves_other_masters_untouched(self):
        other = make_master()
        WorkingHours.objects.create(
            master=other,
            weekday=MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        save_weekly_schedule(self.master, {MONDAY: DaySchedule(works=False)})

        self.assertEqual(
            _hours(other, MONDAY),
            [(time(9, 0), time(18, 0))],
        )

    def test_invalid_day_changes_nothing(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        with self.assertRaises(ValueError):
            save_weekly_schedule(
                self.master,
                {
                    # Этот день корректный и мог бы сохраниться первым...
                    TUESDAY: DaySchedule(
                        works=True,
                        start=time(9, 0),
                        end=time(18, 0),
                    ),
                    # ...но этот заполнен неверно (нет времени).
                    MONDAY: DaySchedule(works=True),
                },
            )

        self.assertEqual(_hours(self.master, TUESDAY), [])
        self.assertEqual(
            _hours(self.master, MONDAY),
            [(time(9, 0), time(18, 0))],
        )

    def test_unknown_weekday_raises_value_error(self):
        with self.assertRaises(ValueError):
            save_weekly_schedule(self.master, {7: DaySchedule(works=False)})
