from datetime import date, time

from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from catalog.models import Absence, Master, WorkDay
from catalog.tests.factories import make_master


# ---------------------------------------------------------------------------
# WorkDay: чистая логика (без базы)
# ---------------------------------------------------------------------------


class WorkDayLogicTests(SimpleTestCase):
    def make(self, **kwargs):
        defaults = dict(
            date=date(2026, 10, 5),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        defaults.update(kwargs)
        return WorkDay(**defaults)

    def test_intervals_without_break(self):
        self.assertEqual(
            self.make().get_intervals(),
            [(time(9, 0), time(18, 0))],
        )

    def test_intervals_with_break(self):
        day = self.make(break_start=time(13, 0), break_end=time(14, 0))

        self.assertEqual(
            day.get_intervals(),
            [(time(9, 0), time(13, 0)), (time(14, 0), time(18, 0))],
        )

    def test_valid_day_passes_clean(self):
        self.make(break_start=time(13, 0), break_end=time(14, 0)).clean()

    def test_clean_rejects_end_before_start(self):
        with self.assertRaises(ValidationError):
            self.make(start_time=time(18, 0), end_time=time(9, 0)).clean()

    def test_clean_rejects_break_with_only_one_side(self):
        with self.assertRaises(ValidationError):
            self.make(break_start=time(13, 0)).clean()

    def test_clean_rejects_reversed_break(self):
        with self.assertRaises(ValidationError):
            self.make(break_start=time(14, 0), break_end=time(13, 0)).clean()

    def test_clean_rejects_break_outside_working_time(self):
        with self.assertRaises(ValidationError):
            self.make(break_start=time(17, 0), break_end=time(19, 0)).clean()


# ---------------------------------------------------------------------------
# WorkDay: ограничения в базе
# ---------------------------------------------------------------------------


class WorkDayDatabaseTests(TestCase):
    def setUp(self):
        self.master = make_master()

    def create(self, **kwargs):
        defaults = dict(
            master=self.master,
            date=date(2026, 10, 5),
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        defaults.update(kwargs)
        return WorkDay.objects.create(**defaults)

    def test_one_work_day_per_master_and_date(self):
        self.create()

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create()

    def test_same_date_is_allowed_for_different_masters(self):
        self.create()
        self.create(master=make_master())

        self.assertEqual(WorkDay.objects.count(), 2)

    def test_database_rejects_end_before_start(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create(start_time=time(18, 0), end_time=time(9, 0))

    def test_database_rejects_break_with_only_one_side(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create(break_start=time(13, 0))

    def test_database_rejects_break_outside_working_time(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create(break_start=time(17, 0), break_end=time(19, 0))

    def test_database_accepts_valid_break(self):
        day = self.create(break_start=time(13, 0), break_end=time(14, 0))

        day.refresh_from_db()
        self.assertEqual(day.break_start, time(13, 0))


# ---------------------------------------------------------------------------
# Absence
# ---------------------------------------------------------------------------


class AbsenceTests(TestCase):
    def setUp(self):
        self.master = make_master()

    def create(self, start, end, master=None, **kwargs):
        return Absence.objects.create(
            master=master or self.master,
            start_date=start,
            end_date=end,
            **kwargs,
        )

    def test_default_kind_is_vacation(self):
        absence = self.create(date(2026, 10, 10), date(2026, 10, 17))

        self.assertEqual(absence.kind, Absence.Kind.VACATION)

    def test_clean_rejects_end_before_start(self):
        absence = Absence(
            master=self.master,
            start_date=date(2026, 10, 17),
            end_date=date(2026, 10, 10),
        )

        with self.assertRaises(ValidationError):
            absence.clean()

    def test_database_rejects_end_before_start(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create(date(2026, 10, 17), date(2026, 10, 10))

    def test_single_day_absence_is_allowed(self):
        absence = self.create(date(2026, 10, 10), date(2026, 10, 10))

        absence.clean()

    def test_clean_rejects_overlap_with_other_absence_of_same_master(self):
        self.create(date(2026, 10, 10), date(2026, 10, 17))
        overlapping = Absence(
            master=self.master,
            start_date=date(2026, 10, 15),
            end_date=date(2026, 10, 20),
        )

        with self.assertRaises(ValidationError):
            overlapping.clean()

    def test_clean_allows_adjacent_absences(self):
        self.create(date(2026, 10, 10), date(2026, 10, 17))
        adjacent = Absence(
            master=self.master,
            start_date=date(2026, 10, 18),
            end_date=date(2026, 10, 20),
        )

        adjacent.clean()

    def test_clean_allows_same_dates_for_different_masters(self):
        self.create(date(2026, 10, 10), date(2026, 10, 17))
        other = Absence(
            master=make_master(),
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 17),
        )

        other.clean()

    def test_clean_does_not_overlap_with_itself_when_editing(self):
        absence = self.create(date(2026, 10, 10), date(2026, 10, 17))
        absence.end_date = date(2026, 10, 18)

        absence.clean()

    def test_clean_works_for_unsaved_master(self):
        absence = Absence(
            master=Master(name="Новый", slug="novyj"),
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 17),
        )

        absence.clean()
