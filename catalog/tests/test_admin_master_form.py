from datetime import time

from django.test import TestCase

from catalog.admin import MasterAdminForm, day_field_name
from catalog.models import Master, WorkingHours
from catalog.services.weekly_schedule import DaySchedule, get_weekly_schedule
from catalog.tests.factories import make_master

MONDAY = WorkingHours.Weekday.MONDAY
TUESDAY = WorkingHours.Weekday.TUESDAY
SATURDAY = WorkingHours.Weekday.SATURDAY


def week_data(week):
    """
    Превращает недельный график в данные формы, как их шлёт браузер.
    Поле дня состоит из пяти частей: day0_0 (галочка), day0_1 (начало),
    day0_2 (конец), day0_3 (перерыв с), day0_4 (перерыв до).
    """
    data = {}

    for weekday, day in week.items():
        name = day_field_name(weekday)

        if day.works:
            data[f"{name}_0"] = "on"

        times = (day.start, day.end, day.break_start, day.break_end)
        for index, value in enumerate(times, start=1):
            data[f"{name}_{index}"] = value.strftime("%H:%M:%S") if value else ""

    return data


def make_form(master, week):
    data = {
        "name": master.name,
        "slug": master.slug,
        "is_active": "on",
        "sort_order": "0",
        "bio": "",
        **week_data(week),
    }

    return MasterAdminForm(data=data, instance=master)


def hours_of(master, weekday):
    return list(
        WorkingHours.objects.filter(master=master, weekday=weekday)
        .order_by("start_time")
        .values_list("start_time", "end_time")
    )


class MasterAdminFormTests(TestCase):
    def setUp(self):
        self.master = make_master()

    def test_initial_values_come_from_saved_week(self):
        for start, end in [(time(9, 0), time(13, 0)), (time(14, 0), time(18, 0))]:
            WorkingHours.objects.create(
                master=self.master,
                weekday=MONDAY,
                start_time=start,
                end_time=end,
            )

        form = MasterAdminForm(instance=self.master)

        self.assertEqual(
            form.initial[day_field_name(MONDAY)],
            DaySchedule(
                works=True,
                start=time(9, 0),
                end=time(18, 0),
                break_start=time(13, 0),
                break_end=time(14, 0),
            ),
        )
        self.assertFalse(form.initial[day_field_name(TUESDAY)].works)

    def test_form_is_invalid_when_working_day_has_no_times(self):
        week = get_weekly_schedule(self.master)
        week[MONDAY] = DaySchedule(works=True)

        form = make_form(self.master, week)

        self.assertFalse(form.is_valid())
        self.assertIn(day_field_name(MONDAY), form.errors)

    def test_form_is_invalid_when_break_is_outside_working_time(self):
        week = get_weekly_schedule(self.master)
        week[MONDAY] = DaySchedule(
            works=True,
            start=time(9, 0),
            end=time(18, 0),
            break_start=time(17, 0),
            break_end=time(19, 0),
        )

        form = make_form(self.master, week)

        self.assertFalse(form.is_valid())

    def test_save_week_saves_changed_day_with_break(self):
        week = get_weekly_schedule(self.master)
        week[MONDAY] = DaySchedule(
            works=True,
            start=time(9, 0),
            end=time(18, 0),
            break_start=time(13, 0),
            break_end=time(14, 0),
        )

        form = make_form(self.master, week)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        form.save_week()

        self.assertEqual(
            hours_of(self.master, MONDAY),
            [(time(9, 0), time(13, 0)), (time(14, 0), time(18, 0))],
        )

    def test_save_week_can_turn_working_day_into_day_off(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=SATURDAY,
            start_time=time(10, 0),
            end_time=time(15, 0),
        )
        week = get_weekly_schedule(self.master)
        week[SATURDAY] = DaySchedule(works=False)

        form = make_form(self.master, week)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        form.save_week()

        self.assertEqual(hours_of(self.master, SATURDAY), [])

    def test_save_week_does_not_touch_unchanged_days(self):
        # В базе у понедельника три интервала — форма умеет показать только
        # один перерыв. Если админ понедельник не трогал, он не должен
        # перезаписаться и потерять второй перерыв.
        three_intervals = [
            (time(9, 0), time(11, 0)),
            (time(12, 0), time(15, 0)),
            (time(16, 0), time(18, 0)),
        ]
        for start, end in three_intervals:
            WorkingHours.objects.create(
                master=self.master,
                weekday=MONDAY,
                start_time=start,
                end_time=end,
            )

        week = get_weekly_schedule(self.master)
        week[TUESDAY] = DaySchedule(works=True, start=time(10, 0), end=time(16, 0))

        form = make_form(self.master, week)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        form.save_week()

        self.assertEqual(hours_of(self.master, MONDAY), three_intervals)
        self.assertEqual(
            hours_of(self.master, TUESDAY),
            [(time(10, 0), time(16, 0))],
        )

    def test_new_master_gets_week_saved_together_with_master(self):
        master = Master(name="Новый мастер", slug="novyj-master")
        week = get_weekly_schedule(master)
        week[MONDAY] = DaySchedule(works=True, start=time(9, 0), end=time(18, 0))

        form = make_form(master, week)
        self.assertTrue(form.is_valid(), form.errors)
        saved_master = form.save()
        form.save_week()

        self.assertIsNotNone(saved_master.pk)
        self.assertEqual(
            hours_of(saved_master, MONDAY),
            [(time(9, 0), time(18, 0))],
        )
