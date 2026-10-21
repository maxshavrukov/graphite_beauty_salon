"""
Шаг сетки онлайн-записи (BOOKING_SLOT_STEP_MINUTES).

Клиент видит время с одним шагом, и запись создаётся с тем же шагом:
нельзя записаться с сайта на время, которого в списке не было.
"""

from datetime import time, timedelta
from typing import Any, cast

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from catalog.models import Booking
from catalog.services import get_slot_step
from catalog.tests.factories import (
    make_master,
    make_master_service,
    make_service,
    make_work_day,
)


class SlotStepTests(TestCase):
    def setUp(self) -> None:
        self.api = APIClient()
        self.service = make_service(slug="haircut")
        self.master = make_master(slug="viktor", name="Виктор")
        make_master_service(self.master, self.service, price=450, duration=30)

        self.target_date = timezone.localdate() + timedelta(days=1)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(11, 0),
        )

    def get(self, url: str, **params: Any) -> Response:
        return cast(Response, self.api.get(url, params))

    def book(self, start_time: str) -> Response:
        payload = {
            "master": "viktor",
            "service": "haircut",
            "date": self.target_date.isoformat(),
            "start_time": start_time,
            "client_name": "Иван",
            "client_phone": "0990172668",
        }
        return cast(Response, self.api.post("/api/bookings/", payload, format="json"))

    def test_default_step_is_thirty_minutes(self) -> None:
        with override_settings():
            del settings.BOOKING_SLOT_STEP_MINUTES

            self.assertEqual(get_slot_step(), 30)

    @override_settings(BOOKING_SLOT_STEP_MINUTES=30)
    def test_service_times_follow_the_step(self) -> None:
        response = self.get(
            "/api/services/haircut/available-times/",
            date=self.target_date.isoformat(),
        )

        self.assertEqual(response.data, ["09:00", "09:30", "10:00", "10:30"])

    @override_settings(BOOKING_SLOT_STEP_MINUTES=30)
    def test_master_times_follow_the_step(self) -> None:
        response = self.get(
            "/api/masters/viktor/services/haircut/available-times/",
            date=self.target_date.isoformat(),
        )

        self.assertEqual(response.data, ["09:00", "09:30", "10:00", "10:30"])

    @override_settings(BOOKING_SLOT_STEP_MINUTES=15)
    def test_step_is_a_setting_not_a_constant(self) -> None:
        response = self.get(
            "/api/services/haircut/available-times/",
            date=self.target_date.isoformat(),
        )

        data = cast(list[str], response.data)
        self.assertIn("09:15", data)

    @override_settings(BOOKING_SLOT_STEP_MINUTES=30)
    def test_masters_are_offered_only_for_times_on_the_grid(self) -> None:
        url = "/api/services/haircut/available-masters/"
        day = self.target_date.isoformat()

        on_grid = self.get(url, date=day, time="09:30")
        off_grid = self.get(url, date=day, time="09:15")

        self.assertEqual(len(cast(list[Any], on_grid.data)), 1)
        self.assertEqual(cast(list[Any], off_grid.data), [])

    @override_settings(BOOKING_SLOT_STEP_MINUTES=30)
    def test_online_booking_off_the_grid_is_rejected(self) -> None:
        response = self.book("09:15")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.count(), 0)

    @override_settings(BOOKING_SLOT_STEP_MINUTES=30)
    def test_online_booking_on_the_grid_is_accepted(self) -> None:
        response = self.book("09:30")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.get().start_time, time(9, 30))
