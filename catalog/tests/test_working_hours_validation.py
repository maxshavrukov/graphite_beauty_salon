from datetime import time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import WorkingHours
from catalog.tests.factories import make_master


class WorkingHoursCleanTests(TestCase):
    def setUp(self):
        self.master = make_master()

    def test_raises_when_end_before_start(self):
        wh = WorkingHours(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(18, 0),
            end_time=time(9, 0),
        )

        with self.assertRaises(ValidationError):
            wh.clean()

    def test_raises_when_end_equals_start(self):
        wh = WorkingHours(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(9, 0),
        )

        with self.assertRaises(ValidationError):
            wh.clean()

    def test_raises_when_overlapping_existing_interval_same_day(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        overlapping = WorkingHours(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(10, 0),
            end_time=time(12, 0),
        )

        with self.assertRaises(ValidationError):
            overlapping.clean()

    def test_allows_touching_intervals_same_day(self):
        # 9:00-13:00 и 13:00-18:00 — не пересекаются, только касаются.
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(13, 0),
        )
        touching = WorkingHours(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(13, 0),
            end_time=time(18, 0),
        )

        touching.clean()  # не должно бросить исключение

    def test_allows_same_times_on_different_weekday(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        other_day = WorkingHours(
            master=self.master,
            weekday=WorkingHours.Weekday.TUESDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        other_day.clean()  # не должно бросить исключение

    def test_allows_same_times_for_different_master(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )
        other_master = make_master()
        same_time_other_master = WorkingHours(
            master=other_master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        same_time_other_master.clean()  # не должно бросить исключение

    def test_editing_existing_instance_does_not_conflict_with_itself(self):
        existing = WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(18, 0),
        )

        existing.end_time = time(19, 0)
        existing.clean()  # не должно бросить исключение о пересечении с собой


class WorkingHoursAdminValidationTests(TestCase):
    """
    Проверка, что защита реально работает через ту самую форму,
    которой владелец салона пользуется на практике — админку,
    а не только при вызове .clean() напрямую из кода.
    """

    def setUp(self):
        self.master = make_master()
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(
            "admin", "admin@example.com", "password123",
        )
        self.client.force_login(self.admin_user)

    def test_admin_rejects_overlapping_working_hours(self):
        WorkingHours.objects.create(
            master=self.master,
            weekday=WorkingHours.Weekday.MONDAY,
            start_time=time(9, 0),
            end_time=time(11, 0),
        )

        response = self.client.post(
            "/admin/catalog/workinghours/add/",
            {
                "master": self.master.pk,
                "weekday": WorkingHours.Weekday.MONDAY,
                "start_time": "10:00:00",
                "end_time": "12:00:00",
            },
        )

        # Форма с ошибкой возвращает 200 (перерисовывает страницу),
        # а не 302 (редирект после успешного сохранения).
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkingHours.objects.count(), 1)
