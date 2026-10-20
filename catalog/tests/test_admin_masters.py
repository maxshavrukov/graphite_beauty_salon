from datetime import date
from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Absence, Master
from catalog.tests.factories import make_master, make_master_service, make_work_day


def management_form(prefix: str, total: int = 0, initial: int = 0) -> dict[str, str]:
    """Служебные поля, без которых админка не принимает блок-вкладку."""
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


class MasterAdminTests(TestCase):
    def setUp(self) -> None:
        user_model: Any = get_user_model()
        user = user_model.objects.create_superuser(
            username="admin-test",
            email="admin-test@example.com",
            password="pass12345",
        )
        self.client.force_login(user)

    def test_master_list_page_opens(self) -> None:
        make_master()

        response = self.client.get(reverse("admin:catalog_master_changelist"))

        self.assertEqual(response.status_code, 200)

    def test_add_page_opens(self) -> None:
        response = self.client.get(reverse("admin:catalog_master_add"))

        self.assertEqual(response.status_code, 200)

    def test_change_page_opens_for_master_with_services_and_work_days(self) -> None:
        master = make_master()
        make_master_service(master)
        make_work_day(master, date(2026, 10, 5))

        response = self.client.get(
            reverse("admin:catalog_master_change", args=[master.pk]),
        )

        self.assertEqual(response.status_code, 200)

    def test_master_can_be_created_together_with_absence(self) -> None:
        # Тот же сценарий, что когда-то ломался с «графиком»: мастера
        # ещё нет в базе, а блок «Отпуск» проверяется до его сохранения.
        data = {
            "name": "Новый мастер",
            "slug": "novyj-master",
            "bio": "",
            "is_active": "on",
            "sort_order": "0",
            **management_form("master_services"),
            **management_form("time_blocks"),
            **management_form("absences", total=1),
            "absences-0-id": "",
            "absences-0-master": "",
            "absences-0-kind": Absence.Kind.VACATION,
            "absences-0-start_date": "2026-10-10",
            "absences-0-end_date": "2026-10-17",
            "absences-0-comment": "Отпуск",
        }

        response = self.client.post(reverse("admin:catalog_master_add"), data)

        self.assertEqual(response.status_code, 302)
        master = Master.objects.get(slug="novyj-master")
        absence = Absence.objects.get(master=master)
        self.assertEqual(absence.start_date, date(2026, 10, 10))
        self.assertEqual(absence.end_date, date(2026, 10, 17))
