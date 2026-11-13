from datetime import time, timedelta
from typing import cast

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from catalog.models import Booking
from catalog.services import SlotUnavailableError, validate_booking_slot
from catalog.tests.factories import (
    make_category,
    make_master,
    make_master_service,
    make_service,
    make_work_day,
)

BOOKINGS_URL = "/api/bookings/"
CATEGORIES_URL = "/api/categories/"


class InactiveCategoryTests(TestCase):
    """Выключенная категория скрывает услуги с сайта и из онлайн-записи."""

    def setUp(self) -> None:
        self.api = APIClient()
        self.category = make_category(name="Ногтевой сервис")
        self.service = make_service(self.category, slug="manicure")
        self.master = make_master(slug="karina")
        make_master_service(self.master, self.service, price=600, duration=30)

        self.target_date = timezone.localdate() + timedelta(days=1)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(11, 0),
        )

    # --- Удобные типизированные хелперы для запросов ---

    def get(self, url: str) -> Response:
        return cast(Response, self.api.get(url))

    def post(self, url: str, data: dict, format: str | None = "json") -> Response:
        if format is None:
            return cast(Response, self.api.post(url, data))
        return cast(Response, self.api.post(url, data, format=format))

    # --- Генераторы путей и данных ---

    def disable_category(self) -> None:
        self.category.is_active = False
        self.category.save()

    def payload(self) -> dict[str, str | int]:
        return {
            "master": self.master.slug,
            "service": self.service.slug,
            "date": self.target_date.isoformat(),
            "start_time": "09:00",
            "client_name": "Иван",
            "client_phone": "+380501234567",
        }

    @property
    def for_service_url(self) -> str:
        return f"/api/services/{self.service.slug}"

    @property
    def for_master_url(self) -> str:
        return f"/api/masters/{self.master.slug}"

    # --- Тесты ---

    def test_active_category_works(self) -> None:
        dates = self.get(f"{self.for_service_url}/available-dates/")
        created = self.post(BOOKINGS_URL, self.payload())

        self.assertEqual(dates.status_code, 200)
        self.assertEqual(created.status_code, 201)

    def test_category_is_hidden_from_catalog(self) -> None:
        self.disable_category()

        response = self.get(CATEGORIES_URL)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Ногтевой сервис", response.content.decode())

    def test_master_services_do_not_include_service(self) -> None:
        self.disable_category()

        response = self.get(f"{self.for_master_url}/services/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_availability_endpoints_return_404(self) -> None:
        self.disable_category()
        day = self.target_date.isoformat()

        urls = [
            f"{self.for_service_url}/available-dates/",
            f"{self.for_service_url}/available-times/?date={day}",
            f"{self.for_service_url}/available-masters/?date={day}&time=09:00",
            f"{self.for_master_url}/services/{self.service.slug}/available-dates/",
            f"{self.for_master_url}/services/{self.service.slug}/available-times/?date={day}",
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.get(url).status_code, 404)

    def test_online_booking_is_rejected(self) -> None:
        self.disable_category()

        response = self.post(BOOKINGS_URL, self.payload())

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Booking.objects.exists())

    def test_online_validation_fails_but_phone_and_admin_pass(self) -> None:
        self.disable_category()

        with self.assertRaises(SlotUnavailableError):
            validate_booking_slot(
                self.master,
                self.service,
                self.target_date,
                time(9, 0),
                Booking.Source.ONLINE,
            )

        for source in (Booking.Source.PHONE, Booking.Source.ADMIN):
            with self.subTest(source=source):
                validate_booking_slot(
                    self.master,
                    self.service,
                    self.target_date,
                    time(9, 0),
                    source,
                )
