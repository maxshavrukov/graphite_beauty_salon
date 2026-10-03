from datetime import time, timedelta
from typing import cast

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from catalog.models import Booking
from catalog.tests.factories import (
    make_booking,
    make_master,
    make_master_service,
    make_service,
    make_work_day,
)

URL = "/api/bookings/"


class BookingCreateApiTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.service = make_service(slug="haircut")
        self.master = make_master(slug="viktor", name="Виктор")
        make_master_service(self.master, self.service, price=450, duration=30)

        # Завтра — гарантированно внутри окна записи.
        self.target_date = timezone.localdate() + timedelta(days=1)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

    # APIClient.post/get для Pylance возвращают не DRF Response
    # (HttpResponse или вовсе WSGIRequest), хотя на деле это он —
    # уточняем тип в одном месте, а не в каждом тесте.
    def post(self, data) -> Response:
        return cast(Response, self.api.post(URL, data, format="json"))

    def get(self) -> Response:
        return cast(Response, self.api.get(URL))

    def payload(self, **overrides):
        data = {
            "master": "viktor",
            "service": "haircut",
            "date": self.target_date.isoformat(),
            "start_time": "09:00",
            "client_name": "Иван",
            "client_phone": "+380501234567",
        }
        data.update(overrides)
        return data

    def test_creates_booking_with_new_status_and_online_source(self):
        response = self.post(self.payload())

        self.assertEqual(response.status_code, 201)

        data = response.data
        assert data is not None  # тело ответа при 201 всегда есть
        self.assertEqual(data["status"], Booking.Status.NEW)
        self.assertEqual(data["master"], "Виктор")

        booking = Booking.objects.get()
        self.assertEqual(booking.source, Booking.Source.ONLINE)
        self.assertEqual(booking.price, 450)

    def test_client_cannot_choose_source_or_status(self):
        response = self.post(self.payload(source="ADMIN", status="CONFIRMED"))

        self.assertEqual(response.status_code, 201)

        booking = Booking.objects.get()
        self.assertEqual(booking.source, Booking.Source.ONLINE)
        self.assertEqual(booking.status, Booking.Status.NEW)

    def test_phone_is_normalized(self):
        self.post(self.payload(client_phone="+38 (050) 123-45-67"))

        self.assertEqual(Booking.objects.get().client_phone, "+380501234567")

    def test_returns_409_when_slot_is_taken(self):
        make_booking(
            master=self.master,
            service=self.service,
            target_date=self.target_date,
            start_time=time(9, 0),
            duration=30,
        )

        response = self.post(self.payload())

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Booking.objects.count(), 1)

    def test_returns_400_for_unknown_master(self):
        response = self.post(self.payload(master="nobody"))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_returns_400_for_inactive_master(self):
        self.master.is_active = False
        self.master.save()

        response = self.post(self.payload())

        self.assertEqual(response.status_code, 400)

    def test_returns_400_when_master_does_not_offer_service(self):
        other_service = make_service(slug="coloring")

        response = self.post(self.payload(service=other_service.slug))

        self.assertEqual(response.status_code, 400)

    def test_returns_400_for_date_outside_window(self):
        far_date = timezone.localdate() + timedelta(days=60)

        response = self.post(self.payload(date=far_date.isoformat()))

        self.assertEqual(response.status_code, 400)

    def test_returns_400_for_past_date(self):
        past_date = timezone.localdate() - timedelta(days=1)

        response = self.post(self.payload(date=past_date.isoformat()))

        self.assertEqual(response.status_code, 400)

    def test_returns_400_for_bad_phone(self):
        response = self.post(self.payload(client_phone="123"))

        self.assertEqual(response.status_code, 400)

    def test_returns_400_for_blank_name(self):
        response = self.post(self.payload(client_name="   "))

        self.assertEqual(response.status_code, 400)

    def test_returns_400_for_missing_fields(self):
        response = self.post({})

        self.assertEqual(response.status_code, 400)

    def test_time_outside_working_hours_returns_409(self):
        response = self.post(self.payload(start_time="20:00"))

        self.assertEqual(response.status_code, 409)

    def test_get_is_not_allowed(self):
        response = self.get()

        self.assertEqual(response.status_code, 405)

    def test_booking_create_is_throttled_after_limit(self):
        # Лимит — 10 запросов в час. Шлём заведомо некорректные данные:
        # нам важно не создание записи, а сам факт подсчёта запросов.
        for _ in range(10):
            response = self.post({})
            self.assertEqual(response.status_code, 400)

        response = self.post({})

        self.assertEqual(response.status_code, 429)
