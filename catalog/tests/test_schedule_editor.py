from datetime import date, time, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Absence, Booking, WorkDay
from catalog.services.schedule_editor import (
    STATE_ABSENT,
    STATE_EMPTY,
    STATE_WORKING,
    copy_work_days,
    create_absence,
    extend_schedule,
    find_active_bookings,
    find_active_bookings_in_range,
    get_filled_until,
    get_month_calendar,
    get_schedule_status,
    remove_work_days,
    set_work_days,
)
from catalog.tests.factories import (
    make_absence,
    make_booking,
    make_master,
    make_service,
    make_work_day,
)

MONDAY = date(2026, 10, 5)


def days(start, count):
    return [start + timedelta(days=offset) for offset in range(count)]


def stored(master):
    """Рабочие дни мастера как словарь: дата -> (начало, конец, перерыв с, до)."""
    return {
        work_day.date: (
            work_day.start_time,
            work_day.end_time,
            work_day.break_start,
            work_day.break_end,
        )
        for work_day in WorkDay.objects.filter(master=master)
    }


# ---------------------------------------------------------------------------
# set_work_days
# ---------------------------------------------------------------------------


class SetWorkDaysTests(TestCase):
    def setUp(self):
        self.master = make_master()

    def test_creates_work_days_for_all_dates(self):
        result = set_work_days(self.master, days(MONDAY, 5), time(10, 0), time(19, 0))

        self.assertEqual(result.created, 5)
        self.assertEqual(result.updated, 0)
        self.assertEqual(len(stored(self.master)), 5)

    def test_saves_break(self):
        set_work_days(
            self.master, [MONDAY], time(10, 0), time(19, 0),
            break_start=time(14, 0), break_end=time(14, 30),
        )

        self.assertEqual(
            stored(self.master)[MONDAY],
            (time(10, 0), time(19, 0), time(14, 0), time(14, 30)),
        )

    def test_updates_time_of_already_marked_day(self):
        make_work_day(self.master, MONDAY, time(9, 0), time(18, 0))

        result = set_work_days(self.master, [MONDAY], time(11, 0), time(16, 0))

        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 1)
        self.assertEqual(stored(self.master)[MONDAY][:2], (time(11, 0), time(16, 0)))

    def test_counts_identical_day_as_unchanged(self):
        make_work_day(self.master, MONDAY, time(9, 0), time(18, 0))

        result = set_work_days(self.master, [MONDAY], time(9, 0), time(18, 0))

        self.assertEqual(result.unchanged, 1)
        self.assertEqual(result.updated, 0)

    def test_mixes_new_updated_and_unchanged_days(self):
        make_work_day(self.master, MONDAY, time(9, 0), time(18, 0))
        make_work_day(self.master, MONDAY + timedelta(days=1), time(10, 0), time(19, 0))

        result = set_work_days(
            self.master, days(MONDAY, 3), time(10, 0), time(19, 0),
        )

        self.assertEqual((result.created, result.updated, result.unchanged), (1, 1, 1))

    def test_duplicate_dates_are_counted_once(self):
        result = set_work_days(
            self.master, [MONDAY, MONDAY, MONDAY], time(9, 0), time(18, 0),
        )

        self.assertEqual(result.created, 1)

    def test_rejects_end_before_start_and_saves_nothing(self):
        with self.assertRaises(ValidationError):
            set_work_days(self.master, days(MONDAY, 3), time(18, 0), time(9, 0))

        self.assertEqual(WorkDay.objects.count(), 0)

    def test_rejects_break_outside_working_time(self):
        with self.assertRaises(ValidationError):
            set_work_days(
                self.master, [MONDAY], time(9, 0), time(18, 0),
                break_start=time(17, 0), break_end=time(19, 0),
            )

    def test_rejects_break_with_only_one_side(self):
        with self.assertRaises(ValidationError):
            set_work_days(
                self.master, [MONDAY], time(9, 0), time(18, 0),
                break_start=time(13, 0),
            )

    def test_rejects_missing_times(self):
        with self.assertRaises(ValidationError):
            set_work_days(self.master, [MONDAY], None, time(18, 0))

    def test_rejects_empty_date_list(self):
        with self.assertRaises(ValueError):
            set_work_days(self.master, [], time(9, 0), time(18, 0))

    def test_does_not_touch_other_masters_or_dates(self):
        other = make_master()
        make_work_day(other, MONDAY, time(9, 0), time(18, 0))
        make_work_day(self.master, MONDAY + timedelta(days=10), time(9, 0), time(18, 0))

        set_work_days(self.master, [MONDAY], time(12, 0), time(15, 0))

        self.assertEqual(stored(other)[MONDAY][:2], (time(9, 0), time(18, 0)))
        self.assertEqual(
            stored(self.master)[MONDAY + timedelta(days=10)][:2],
            (time(9, 0), time(18, 0)),
        )


# ---------------------------------------------------------------------------
# remove_work_days
# ---------------------------------------------------------------------------


class RemoveWorkDaysTests(TestCase):
    def setUp(self):
        self.master = make_master()
        for day in days(MONDAY, 5):
            make_work_day(self.master, day)

    def test_removes_only_selected_dates(self):
        removed = remove_work_days(self.master, days(MONDAY, 2))

        self.assertEqual(removed, 2)
        self.assertEqual(WorkDay.objects.filter(master=self.master).count(), 3)

    def test_ignores_dates_without_work_day(self):
        removed = remove_work_days(self.master, [MONDAY + timedelta(days=30)])

        self.assertEqual(removed, 0)
        self.assertEqual(WorkDay.objects.filter(master=self.master).count(), 5)

    def test_empty_selection_removes_nothing(self):
        self.assertEqual(remove_work_days(self.master, []), 0)

    def test_does_not_remove_other_masters_days(self):
        other = make_master()
        make_work_day(other, MONDAY)

        remove_work_days(self.master, [MONDAY])

        self.assertEqual(WorkDay.objects.filter(master=other).count(), 1)


# ---------------------------------------------------------------------------
# create_absence
# ---------------------------------------------------------------------------


class CreateAbsenceTests(TestCase):
    def setUp(self):
        self.master = make_master()

    def test_creates_absence(self):
        absence = create_absence(
            self.master, Absence.Kind.SICK,
            date(2026, 10, 10), date(2026, 10, 17), "Грипп",
        )

        self.assertIsNotNone(absence.pk)
        self.assertEqual(absence.kind, Absence.Kind.SICK)
        self.assertEqual(absence.comment, "Грипп")

    def test_rejects_end_before_start(self):
        with self.assertRaises(ValidationError):
            create_absence(
                self.master, Absence.Kind.VACATION,
                date(2026, 10, 17), date(2026, 10, 10),
            )

    def test_rejects_overlap_with_existing_absence(self):
        make_absence(self.master, date(2026, 10, 10), date(2026, 10, 17))

        with self.assertRaises(ValidationError):
            create_absence(
                self.master, Absence.Kind.DAY_OFF,
                date(2026, 10, 15), date(2026, 10, 20),
            )

        self.assertEqual(Absence.objects.count(), 1)

    def test_rejects_unknown_kind(self):
        with self.assertRaises(ValidationError):
            create_absence(self.master, "WRONG", MONDAY, MONDAY)

    def test_keeps_work_days_inside_the_period(self):
        make_work_day(self.master, MONDAY)

        create_absence(self.master, Absence.Kind.VACATION, MONDAY, MONDAY)

        self.assertEqual(WorkDay.objects.filter(master=self.master).count(), 1)


# ---------------------------------------------------------------------------
# find_active_bookings
# ---------------------------------------------------------------------------


class FindActiveBookingsTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.service = make_service()

    def booking(self, target_date, hour, **kwargs):
        return make_booking(
            master=kwargs.pop("master", self.master),
            service=self.service,
            target_date=target_date,
            start_time=time(hour, 0),
            **kwargs,
        )

    def test_returns_new_and_confirmed_in_time_order(self):
        late = self.booking(MONDAY, 15, status=Booking.Status.CONFIRMED)
        early = self.booking(MONDAY, 9)

        result = find_active_bookings(self.master, [MONDAY])

        self.assertEqual(result, [early, late])

    def test_excludes_closed_statuses(self):
        for hour, status in (
            (9, Booking.Status.CANCELLED),
            (10, Booking.Status.COMPLETED),
            (11, Booking.Status.NO_SHOW),
        ):
            self.booking(MONDAY, hour, status=status)

        self.assertEqual(find_active_bookings(self.master, [MONDAY]), [])

    def test_only_selected_dates_and_master(self):
        wanted = self.booking(MONDAY, 9)
        self.booking(MONDAY + timedelta(days=1), 9)
        self.booking(MONDAY, 10, master=make_master())

        self.assertEqual(find_active_bookings(self.master, [MONDAY]), [wanted])

    def test_empty_dates_give_empty_result(self):
        self.assertEqual(find_active_bookings(self.master, []), [])

    def test_range_includes_both_boundaries(self):
        first = self.booking(MONDAY, 9)
        last = self.booking(MONDAY + timedelta(days=2), 9)
        self.booking(MONDAY + timedelta(days=3), 9)

        result = find_active_bookings_in_range(
            self.master, MONDAY, MONDAY + timedelta(days=2),
        )

        self.assertEqual(result, [first, last])


# ---------------------------------------------------------------------------
# «Расписание заполнено до …»
# ---------------------------------------------------------------------------


class ScheduleStatusTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.today = date(2026, 10, 5)

    def status(self, **kwargs):
        return get_schedule_status(self.master, today=self.today, **kwargs)

    def test_new_master_has_no_filled_until_and_is_low(self):
        status = self.status()

        self.assertIsNone(status.filled_until)
        self.assertEqual(status.days_left, 0)
        self.assertTrue(status.is_low)

    def test_filled_until_is_the_last_work_day(self):
        make_work_day(self.master, MONDAY)
        make_work_day(self.master, MONDAY + timedelta(days=9))
        make_work_day(self.master, MONDAY + timedelta(days=3))

        self.assertEqual(get_filled_until(self.master), MONDAY + timedelta(days=9))

    def test_far_enough_schedule_is_not_low(self):
        make_work_day(self.master, self.today + timedelta(days=30))

        status = self.status()

        self.assertEqual(status.days_left, 30)
        self.assertFalse(status.is_low)

    def test_exactly_on_threshold_is_not_low(self):
        make_work_day(self.master, self.today + timedelta(days=21))

        self.assertFalse(self.status().is_low)

    def test_one_day_below_threshold_is_low(self):
        make_work_day(self.master, self.today + timedelta(days=20))

        self.assertTrue(self.status().is_low)

    def test_schedule_ending_in_the_past_has_no_days_left(self):
        make_work_day(self.master, self.today - timedelta(days=3))

        status = self.status()

        self.assertEqual(status.days_left, 0)
        self.assertTrue(status.is_low)

    def test_threshold_can_be_overridden(self):
        make_work_day(self.master, self.today + timedelta(days=10))

        self.assertTrue(self.status().is_low)
        self.assertFalse(self.status(warning_days=7).is_low)


# ---------------------------------------------------------------------------
# copy_work_days и extend_schedule
# ---------------------------------------------------------------------------


class CopyWorkDaysTests(TestCase):
    def setUp(self):
        self.master = make_master()
        for day in days(MONDAY, 3):  # пн, вт, ср
            make_work_day(self.master, day, time(10, 0), time(19, 0))

    def copy(self, **kwargs):
        return copy_work_days(
            self.master, MONDAY, MONDAY + timedelta(days=6), shift_weeks=2, **kwargs,
        )

    def test_copies_forward_keeping_weekdays(self):
        result = self.copy()

        self.assertEqual(result.created, 3)
        for day in days(MONDAY + timedelta(days=14), 3):
            self.assertIn(day, stored(self.master))
            self.assertEqual(day.weekday(), (day - timedelta(days=14)).weekday())

    def test_copies_times_and_break(self):
        WorkDay.objects.filter(master=self.master, date=MONDAY).update(
            break_start=time(14, 0), break_end=time(14, 30),
        )

        self.copy()

        self.assertEqual(
            stored(self.master)[MONDAY + timedelta(days=14)],
            (time(10, 0), time(19, 0), time(14, 0), time(14, 30)),
        )

    def test_skips_already_marked_dates_by_default(self):
        target = MONDAY + timedelta(days=14)
        make_work_day(self.master, target, time(8, 0), time(12, 0))

        result = self.copy()

        self.assertEqual((result.created, result.skipped, result.replaced), (2, 1, 0))
        self.assertEqual(stored(self.master)[target][:2], (time(8, 0), time(12, 0)))

    def test_overwrite_replaces_already_marked_dates(self):
        target = MONDAY + timedelta(days=14)
        make_work_day(self.master, target, time(8, 0), time(12, 0))

        result = self.copy(overwrite=True)

        self.assertEqual((result.created, result.replaced, result.skipped), (2, 1, 0))
        self.assertEqual(stored(self.master)[target][:2], (time(10, 0), time(19, 0)))

    def test_absences_are_not_copied(self):
        make_absence(self.master, MONDAY, MONDAY + timedelta(days=1))

        self.copy()

        self.assertEqual(Absence.objects.count(), 1)

    def test_rejects_zero_shift(self):
        with self.assertRaises(ValueError):
            copy_work_days(self.master, MONDAY, MONDAY, shift_weeks=0)

    def test_rejects_reversed_period(self):
        with self.assertRaises(ValueError):
            copy_work_days(self.master, MONDAY + timedelta(days=1), MONDAY, shift_weeks=1)


class ExtendScheduleTests(TestCase):
    def setUp(self):
        self.master = make_master()
        # Четыре недели, пн–пт: с 5 по 30 октября 2026.
        for week in range(4):
            for offset in range(5):
                make_work_day(self.master, MONDAY + timedelta(days=7 * week + offset))

    def test_continues_schedule_for_four_weeks(self):
        result = extend_schedule(self.master, weeks=4)

        self.assertEqual(result.created, 20)
        self.assertEqual(get_filled_until(self.master), date(2026, 11, 27))
        self.assertIn(date(2026, 11, 2), stored(self.master))  # понедельник
        self.assertNotIn(date(2026, 10, 31), stored(self.master))  # суббота

    def test_second_call_continues_further(self):
        extend_schedule(self.master, weeks=4)

        result = extend_schedule(self.master, weeks=4)

        self.assertEqual(result.created, 20)
        self.assertEqual(get_filled_until(self.master), date(2026, 12, 25))

    def test_works_with_shorter_pattern(self):
        extend_schedule(self.master, weeks=1)

        self.assertEqual(get_filled_until(self.master), date(2026, 11, 6))

    def test_master_without_schedule_cannot_be_extended(self):
        with self.assertRaises(ValidationError):
            extend_schedule(make_master())

    def test_rejects_non_positive_weeks(self):
        with self.assertRaises(ValueError):
            extend_schedule(self.master, weeks=0)


# ---------------------------------------------------------------------------
# get_month_calendar
# ---------------------------------------------------------------------------


class GetMonthCalendarTests(TestCase):
    def setUp(self):
        self.master = make_master()
        self.service = make_service()

    def calendar(self, today=date(2026, 10, 1)):
        return get_month_calendar(self.master, 2026, 10, today=today)

    def day(self, number, **kwargs):
        return self.calendar(**kwargs)[number - 1]

    def test_contains_every_day_of_the_month(self):
        result = self.calendar()

        self.assertEqual(len(result), 31)
        self.assertEqual(result[0].day, date(2026, 10, 1))
        self.assertEqual(result[-1].day, date(2026, 10, 31))

    def test_leap_february_has_29_days(self):
        result = get_month_calendar(self.master, 2028, 2, today=date(2028, 1, 1))

        self.assertEqual(len(result), 29)

    def test_empty_day_when_master_is_not_marked(self):
        self.assertEqual(self.day(5).state, STATE_EMPTY)

    def test_working_day_carries_its_times(self):
        make_work_day(
            self.master, MONDAY, time(10, 0), time(19, 0),
            break_start=time(14, 0), break_end=time(14, 30),
        )

        result = self.day(5)

        self.assertEqual(result.state, STATE_WORKING)
        work_day = result.work_day
        assert work_day is not None
        self.assertEqual(work_day.start_time, time(10, 0))
        self.assertEqual(work_day.break_start, time(14, 0))

    def test_absence_covers_its_dates_including_boundaries(self):
        make_absence(self.master, date(2026, 10, 10), date(2026, 10, 12))

        self.assertEqual(self.day(9).state, STATE_EMPTY)
        self.assertEqual(self.day(10).state, STATE_ABSENT)
        self.assertEqual(self.day(11).state, STATE_ABSENT)
        self.assertEqual(self.day(12).state, STATE_ABSENT)
        self.assertEqual(self.day(13).state, STATE_EMPTY)

    def test_absence_started_in_previous_month_is_shown(self):
        make_absence(self.master, date(2026, 9, 28), date(2026, 10, 3))

        self.assertEqual(self.day(1).state, STATE_ABSENT)
        self.assertEqual(self.day(3).state, STATE_ABSENT)
        self.assertEqual(self.day(4).state, STATE_EMPTY)

    def test_absence_wins_over_work_day_but_keeps_it(self):
        make_work_day(self.master, MONDAY)
        make_absence(self.master, MONDAY)

        result = self.day(5)

        self.assertEqual(result.state, STATE_ABSENT)
        self.assertIsNotNone(result.work_day)
        absence = result.absence
        assert absence is not None
        self.assertEqual(absence.kind, Absence.Kind.VACATION)

    def test_bookings_count_includes_only_active_ones_of_this_master(self):
        for hour, status in (
            (9, Booking.Status.NEW),
            (10, Booking.Status.CONFIRMED),
            (11, Booking.Status.CANCELLED),
        ):
            make_booking(
                master=self.master, service=self.service,
                target_date=MONDAY, start_time=time(hour, 0), status=status,
            )
        make_booking(
            master=self.master, service=self.service,
            target_date=MONDAY + timedelta(days=1), start_time=time(9, 0),
        )
        make_booking(
            master=make_master(), service=self.service,
            target_date=MONDAY, start_time=time(9, 0),
        )

        self.assertEqual(self.day(5).bookings_count, 2)
        self.assertEqual(self.day(6).bookings_count, 1)
        self.assertEqual(self.day(7).bookings_count, 0)

    def test_today_and_past_flags(self):
        today = date(2026, 10, 10)

        self.assertTrue(self.day(9, today=today).is_past)
        self.assertFalse(self.day(9, today=today).is_today)
        self.assertTrue(self.day(10, today=today).is_today)
        self.assertFalse(self.day(10, today=today).is_past)
        self.assertFalse(self.day(11, today=today).is_past)

    def test_uses_three_queries_for_the_whole_month(self):
        make_work_day(self.master, MONDAY)
        make_absence(self.master, MONDAY)
        make_booking(
            master=self.master, service=self.service,
            target_date=MONDAY, start_time=time(9, 0),
        )

        with self.assertNumQueries(3):
            get_month_calendar(self.master, 2026, 10, today=date(2026, 10, 1))
