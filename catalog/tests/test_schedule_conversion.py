"""
Тесты переноса старого расписания (ВРЕМЕННЫЕ: удаляются вместе со старыми
моделями на шаге 2б).
"""

from datetime import date, time
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from catalog.models import ScheduleException, WorkDay, WorkingHours
from catalog.services.schedule_conversion import (
    convert_master_schedule,
    convert_old_schedule,
)
from catalog.tests.factories import make_master

MONDAY = date(2026, 10, 5)
SUNDAY = date(2026, 10, 11)
NEXT_MONDAY = date(2026, 10, 12)


def add_hours(master, weekday, start=time(9, 0), end=time(18, 0)):
    return WorkingHours.objects.create(
        master=master,
        weekday=weekday,
        start_time=start,
        end_time=end,
    )


class ConvertMasterScheduleTests(TestCase):
    def setUp(self):
        self.master = make_master()

    def convert(self, date_from=MONDAY, date_to=SUNDAY, **kwargs):
        return convert_master_schedule(self.master, date_from, date_to, **kwargs)

    def dates(self):
        return list(
            WorkDay.objects.filter(master=self.master).values_list("date", flat=True)
        )

    def test_weekly_template_becomes_work_days_for_working_weekdays_only(self):
        for weekday in range(5):  # пн–пт
            add_hours(self.master, weekday)

        report = self.convert()

        self.assertEqual(report.created, 5)
        self.assertEqual(len(self.dates()), 5)
        self.assertNotIn(date(2026, 10, 10), self.dates())  # суббота
        self.assertNotIn(SUNDAY, self.dates())

    def test_work_day_gets_times_from_template(self):
        add_hours(self.master, 0, time(10, 0), time(19, 0))

        self.convert()

        day = WorkDay.objects.get(master=self.master, date=MONDAY)
        self.assertEqual(day.start_time, time(10, 0))
        self.assertEqual(day.end_time, time(19, 0))
        self.assertIsNone(day.break_start)
        self.assertIsNone(day.break_end)

    def test_two_intervals_become_one_day_with_break(self):
        add_hours(self.master, 0, time(9, 0), time(13, 0))
        add_hours(self.master, 0, time(14, 0), time(18, 0))

        self.convert()

        day = WorkDay.objects.get(master=self.master, date=MONDAY)
        self.assertEqual(day.start_time, time(9, 0))
        self.assertEqual(day.end_time, time(18, 0))
        self.assertEqual(day.break_start, time(13, 0))
        self.assertEqual(day.break_end, time(14, 0))

    def test_closed_exception_removes_work_day(self):
        add_hours(self.master, 0)
        ScheduleException.objects.create(
            master=self.master, date=MONDAY, is_closed=True,
        )

        report = self.convert()

        self.assertEqual(self.dates(), [])
        self.assertEqual(report.closed_days, 1)

    def test_closed_exception_with_reason_is_reported(self):
        ScheduleException.objects.create(
            master=self.master, date=MONDAY, is_closed=True, reason="Врач",
        )

        report = self.convert()

        self.assertEqual(len(report.closed_with_reason), 1)
        self.assertIn("Врач", report.closed_with_reason[0])

    def test_exception_with_special_hours_replaces_template(self):
        add_hours(self.master, 0, time(9, 0), time(18, 0))
        ScheduleException.objects.create(
            master=self.master,
            date=MONDAY,
            is_closed=False,
            start_time=time(12, 0),
            end_time=time(16, 0),
        )

        self.convert()

        day = WorkDay.objects.get(master=self.master, date=MONDAY)
        self.assertEqual(day.start_time, time(12, 0))
        self.assertEqual(day.end_time, time(16, 0))

    def test_exception_with_hours_adds_day_that_template_does_not_have(self):
        # В шаблоне нет воскресенья, но на эту дату есть особые часы.
        ScheduleException.objects.create(
            master=self.master,
            date=SUNDAY,
            is_closed=False,
            start_time=time(10, 0),
            end_time=time(14, 0),
        )

        self.convert()

        self.assertEqual(self.dates(), [SUNDAY])

    def test_existing_work_day_is_not_overwritten(self):
        add_hours(self.master, 0, time(9, 0), time(18, 0))
        WorkDay.objects.create(
            master=self.master,
            date=MONDAY,
            start_time=time(11, 0),
            end_time=time(15, 0),
        )

        report = self.convert()

        day = WorkDay.objects.get(master=self.master, date=MONDAY)
        self.assertEqual(day.start_time, time(11, 0))
        self.assertEqual(report.skipped_existing, 1)
        self.assertEqual(report.created, 0)

    def test_second_run_creates_nothing_new(self):
        add_hours(self.master, 0)
        self.convert()

        report = self.convert()

        self.assertEqual(report.created, 0)
        self.assertEqual(WorkDay.objects.filter(master=self.master).count(), 1)

    def test_dry_run_reports_but_saves_nothing(self):
        add_hours(self.master, 0)

        report = self.convert(dry_run=True)

        self.assertEqual(report.created, 1)
        self.assertEqual(WorkDay.objects.count(), 0)

    def test_period_boundaries_are_inclusive(self):
        add_hours(self.master, 0)  # понедельник

        self.convert(date_from=MONDAY, date_to=NEXT_MONDAY)

        self.assertEqual(sorted(self.dates()), [MONDAY, NEXT_MONDAY])

    def test_master_without_any_hours_gets_nothing(self):
        report = self.convert()

        self.assertEqual(report.created, 0)

    def test_more_than_two_intervals_produce_warning(self):
        add_hours(self.master, 0, time(9, 0), time(11, 0))
        add_hours(self.master, 0, time(12, 0), time(15, 0))
        add_hours(self.master, 0, time(16, 0), time(18, 0))

        report = self.convert()

        self.assertEqual(len(report.warnings), 1)


class ConvertOldScheduleTests(TestCase):
    def test_converts_all_masters_independently(self):
        first = make_master()
        second = make_master()
        add_hours(first, 0)
        add_hours(second, 0)
        add_hours(second, 1)

        report = convert_old_schedule(MONDAY, SUNDAY)

        self.assertEqual(report.created, 3)
        self.assertEqual(WorkDay.objects.filter(master=first).count(), 1)
        self.assertEqual(WorkDay.objects.filter(master=second).count(), 2)


class ConvertCommandTests(TestCase):
    def test_command_creates_work_days_and_prints_summary(self):
        master = make_master()
        add_hours(master, 0)
        out = StringIO()

        call_command(
            "convert_old_schedule",
            "--from-date", "2026-10-05",
            "--days", "6",
            stdout=out,
        )

        self.assertEqual(WorkDay.objects.filter(master=master).count(), 1)
        self.assertIn("Создано рабочих дней: 1", out.getvalue())

    def test_command_dry_run_saves_nothing(self):
        master = make_master()
        add_hours(master, 0)
        out = StringIO()

        call_command(
            "convert_old_schedule",
            "--from-date", "2026-10-05",
            "--days", "6",
            "--dry-run",
            stdout=out,
        )

        self.assertEqual(WorkDay.objects.count(), 0)
        self.assertIn("ПРОБНЫЙ ЗАПУСК", out.getvalue())
