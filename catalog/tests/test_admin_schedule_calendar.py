from datetime import date, time, timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Absence, Booking, WorkDay
from catalog.tests.factories import make_booking, make_master, make_work_day


class ScheduleCalendarTests(TestCase):
    """Страница «Расписание»: выбор дней в календаре и применение времени."""

    def setUp(self) -> None:
        user_model: Any = get_user_model()
        user = user_model.objects.create_superuser(
            username="admin-test",
            email="admin-test@example.com",
            password="pass12345",
        )
        self.client.force_login(user)
        self.url = reverse("admin:catalog_workday_schedule")
        self.today = timezone.localdate()
        self.master = make_master(name="Вадим")

    def _post(self, **overrides):
        day = self.today + timedelta(days=2)
        data = {
            "master": self.master.pk,
            "month": f"{day:%Y-%m}",
            "action": "apply",
            "dates": day.isoformat(),
            "start_time": "10:00:00",
            "end_time": "19:00:00",
            "break_start": "",
            "break_end": "",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_page_opens_and_shows_master(self) -> None:
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Вадим")

    def test_page_opens_with_work_days_absence_and_bookings(self) -> None:
        day = self.today + timedelta(days=1)
        make_work_day(self.master, day, time(9, 0), time(18, 0))
        make_booking(
            master=self.master,
            target_date=day,
            start_time=time(10, 0),
        )
        Absence.objects.create(
            master=self.master,
            kind=Absence.Kind.VACATION,
            start_date=day + timedelta(days=3),
            end_date=day + timedelta(days=4),
        )

        response = self.client.get(
            self.url,
            {"master": self.master.pk, "month": f"{day:%Y-%m}"},
        )

        self.assertEqual(response.status_code, 200)

    def test_unknown_month_and_master_fall_back_to_defaults(self) -> None:
        response = self.client.get(self.url, {"master": "abc", "month": "xx"})

        self.assertEqual(response.status_code, 200)

    def test_page_opens_without_masters(self) -> None:
        self.master.delete()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    def test_anonymous_user_is_redirected_to_login(self) -> None:
        self.client.logout()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_apply_creates_work_days_for_selected_dates(self) -> None:
        first = self.today + timedelta(days=2)
        second = self.today + timedelta(days=3)

        response = self._post(dates=f"{first.isoformat()},{second.isoformat()}")

        self.assertEqual(response.status_code, 302)
        days = WorkDay.objects.filter(master=self.master).order_by("date")
        self.assertEqual([d.date for d in days], [first, second])
        self.assertEqual(days[0].start_time, time(10, 0))
        self.assertEqual(days[0].end_time, time(19, 0))
        self.assertIsNone(days[0].break_start)

    def test_apply_saves_break(self) -> None:
        response = self._post(break_start="13:00:00", break_end="14:00:00")

        self.assertEqual(response.status_code, 302)
        work_day = WorkDay.objects.get(master=self.master)
        self.assertEqual(work_day.break_start, time(13, 0))
        self.assertEqual(work_day.break_end, time(14, 0))

    def test_apply_updates_existing_work_day(self) -> None:
        day = self.today + timedelta(days=2)
        make_work_day(self.master, day, time(9, 0), time(18, 0))

        self._post(dates=day.isoformat())

        work_day = WorkDay.objects.get(master=self.master, date=day)
        self.assertEqual(work_day.start_time, time(10, 0))
        self.assertEqual(work_day.end_time, time(19, 0))
        self.assertEqual(WorkDay.objects.filter(master=self.master).count(), 1)

    def test_apply_without_selected_days_changes_nothing(self) -> None:
        response = self._post(dates="")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkDay.objects.exists())

    def test_apply_rejects_past_days(self) -> None:
        yesterday = self.today - timedelta(days=1)

        response = self._post(dates=yesterday.isoformat())

        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkDay.objects.exists())

    def test_apply_rejects_end_before_start(self) -> None:
        response = self._post(start_time="19:00:00", end_time="10:00:00")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkDay.objects.exists())

    def test_apply_rejects_half_filled_break(self) -> None:
        response = self._post(break_start="13:00:00", break_end="")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkDay.objects.exists())

    def test_apply_cannot_push_online_booking_out_of_work_hours(self) -> None:
        day = self.today + timedelta(days=2)
        make_work_day(self.master, day, time(9, 0), time(18, 0))
        make_booking(
            master=self.master,
            target_date=day,
            start_time=time(16, 0),
            source=Booking.Source.ONLINE,
        )

        response = self._post(
            dates=day.isoformat(),
            start_time="09:00:00",
            end_time="12:00:00",
        )

        self.assertEqual(response.status_code, 200)
        work_day = WorkDay.objects.get(master=self.master, date=day)
        self.assertEqual(work_day.end_time, time(18, 0))

    def test_clear_removes_selected_work_days(self) -> None:
        day = self.today + timedelta(days=2)
        make_work_day(self.master, day)

        response = self._post(action="clear", dates=day.isoformat())

        self.assertEqual(response.status_code, 302)
        self.assertFalse(WorkDay.objects.filter(master=self.master).exists())

    def test_clear_is_blocked_by_online_booking(self) -> None:
        day = self.today + timedelta(days=2)
        make_work_day(self.master, day)
        make_booking(
            master=self.master,
            target_date=day,
            start_time=time(10, 0),
            source=Booking.Source.ONLINE,
        )

        response = self._post(action="clear", dates=day.isoformat())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(WorkDay.objects.filter(master=self.master).exists())

    def test_absence_form_creates_absence(self) -> None:
        start = self.today + timedelta(days=5)
        end = self.today + timedelta(days=7)

        response = self.client.post(
            self.url,
            {
                "master": self.master.pk,
                "month": f"{start:%Y-%m}",
                "action": "absence",
                "kind": Absence.Kind.SICK,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "comment": "Простуда",
            },
        )

        self.assertEqual(response.status_code, 302)
        absence = Absence.objects.get(master=self.master)
        self.assertEqual(absence.kind, Absence.Kind.SICK)
        self.assertEqual(absence.start_date, start)
        self.assertEqual(absence.end_date, end)

    def test_absence_form_rejects_reversed_dates(self) -> None:
        start = self.today + timedelta(days=7)
        end = self.today + timedelta(days=5)

        response = self.client.post(
            self.url,
            {
                "master": self.master.pk,
                "month": f"{start:%Y-%m}",
                "action": "absence",
                "kind": Absence.Kind.VACATION,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Absence.objects.exists())

    def test_unknown_action_changes_nothing(self) -> None:
        response = self._post(action="nonsense")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkDay.objects.exists())

    def test_work_day_list_and_add_pages_still_open(self) -> None:
        make_work_day(self.master, date(2026, 10, 5), time(9, 0), time(18, 0))

        listing = self.client.get(reverse("admin:catalog_workday_changelist"))
        add = self.client.get(reverse("admin:catalog_workday_add"))

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(add.status_code, 200)
