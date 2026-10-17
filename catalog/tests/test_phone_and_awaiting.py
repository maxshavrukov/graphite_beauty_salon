"""
Телефон клиента и список заявок, ожидающих подтверждения.

Админ подтверждает заявки звонком, поэтому номер должен храниться одним
форматом и быть кликабельным, а новые заявки не должны теряться в списке.
"""

from datetime import date, time, timedelta
from typing import cast

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from catalog.admin import BookingChangeForm, BookingCreateForm
from catalog.admin.bookings import format_waiting
from catalog.models import Booking
from catalog.phone import InvalidPhoneError, normalize_ua_phone
from catalog.tests.factories import (
    make_booking,
    make_master,
    make_master_service,
    make_service,
    make_work_day,
)

MONDAY = date(2026, 9, 7)


# ---------------------------------------------------------------------------
# normalize_ua_phone
# ---------------------------------------------------------------------------


class NormalizeUaPhoneTests(SimpleTestCase):
    def test_accepts_the_formats_people_really_type(self):
        variants = [
            "0990172668",  # так клиент вводит после префикса +38 на сайте
            "+380990172668",
            "380990172668",
            "+38 0990172668",
            "+38 (099) 017-26-68",
            "  099 017 26 68  ",
        ]

        for value in variants:
            with self.subTest(value=value):
                self.assertEqual(normalize_ua_phone(value), "+380990172668")

    def test_rejects_everything_else(self):
        invalid = [
            "",
            "   ",
            "123",
            "099017266",  # на цифру короче
            "09901726688",  # на цифру длиннее
            "1990172668",  # 10 цифр, но не с нуля
            "+48501234567",  # не украинский номер
            "+38+380990172668",  # префикс продублирован
            "abcdefghij",
        ]

        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(InvalidPhoneError):
                    normalize_ua_phone(value)


# ---------------------------------------------------------------------------
# Телефон в API записи с сайта
# ---------------------------------------------------------------------------


class PhoneInApiTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.service = make_service(slug="haircut")
        self.master = make_master(slug="viktor", name="Виктор")
        make_master_service(self.master, self.service, price=450, duration=30)

        self.target_date = timezone.localdate() + timedelta(days=1)
        make_work_day(
            master=self.master,
            target_date=self.target_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

    def post(self, phone) -> Response:
        payload = {
            "master": "viktor",
            "service": "haircut",
            "date": self.target_date.isoformat(),
            "start_time": "09:00",
            "client_name": "Иван",
            "client_phone": phone,
        }
        return cast(Response, self.api.post("/api/bookings/", payload, format="json"))

    def test_number_typed_after_plus_38_prefix_is_stored_in_one_format(self):
        response = self.post("0990172668")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Booking.objects.get().client_phone, "+380990172668")

    def test_full_international_number_gives_the_same_result(self):
        self.post("+380990172668")

        self.assertEqual(Booking.objects.get().client_phone, "+380990172668")

    def test_response_has_everything_for_the_wait_for_call_message(self):
        response = self.post("0990172668")

        self.assertEqual(response.status_code, 201)
        data = response.data
        assert data is not None
        # Запись ещё не подтверждена, и сайт покажет, на какой номер позвонят.
        self.assertEqual(data["status"], Booking.Status.NEW)
        self.assertEqual(data["client_name"], "Иван")
        self.assertEqual(data["client_phone"], "+380990172668")

    def test_foreign_or_broken_number_is_rejected(self):
        for phone in ("+48501234567", "099017266", ""):
            with self.subTest(phone=phone):
                response = self.post(phone)

                self.assertEqual(response.status_code, 400)

        self.assertEqual(Booking.objects.count(), 0)


# ---------------------------------------------------------------------------
# Телефон в формах админки
# ---------------------------------------------------------------------------


class PhoneInAdminFormsTests(TestCase):
    def setUp(self):
        self.service = make_service()
        self.master = make_master()
        make_master_service(self.master, self.service, price=450, duration=30)

    def create_data(self, phone):
        return {
            "master": self.master.pk,
            "service": self.service.pk,
            "date": "2026-09-07",
            "start_time": "09:00:00",
            "client_name": "Иван",
            "client_phone": phone,
            "source": Booking.Source.PHONE,
            "comment": "",
        }

    def test_create_form_normalizes_phone(self):
        form = BookingCreateForm(data=self.create_data("099 017 26 68"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_phone"], "+380990172668")

    def test_create_form_rejects_bad_phone(self):
        form = BookingCreateForm(data=self.create_data("12345"))

        self.assertFalse(form.is_valid())
        self.assertIn("client_phone", form.errors)

    def test_change_form_normalizes_phone(self):
        booking = make_booking(
            master=self.master, service=self.service,
            target_date=MONDAY, start_time=time(9, 0),
        )

        form = BookingChangeForm(
            data={
                "client_name": booking.client_name,
                "client_phone": "0990172668",
                "status": booking.status,
                "comment": "",
            },
            instance=booking,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["client_phone"], "+380990172668")

    def test_change_form_rejects_bad_phone(self):
        booking = make_booking(
            master=self.master, service=self.service,
            target_date=MONDAY, start_time=time(9, 0),
        )

        form = BookingChangeForm(
            data={
                "client_name": booking.client_name,
                "client_phone": "123",
                "status": booking.status,
                "comment": "",
            },
            instance=booking,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("client_phone", form.errors)


# ---------------------------------------------------------------------------
# Сколько ждёт заявка
# ---------------------------------------------------------------------------


class FormatWaitingTests(SimpleTestCase):
    def test_formats_by_size(self):
        cases = [
            (timedelta(seconds=20), "только что"),
            (timedelta(minutes=5), "5 мин"),
            (timedelta(minutes=59), "59 мин"),
            (timedelta(hours=3, minutes=40), "3 ч"),
            (timedelta(hours=23, minutes=59), "23 ч"),
            (timedelta(days=2, hours=5), "2 д"),
        ]

        for delta, expected in cases:
            with self.subTest(delta=delta):
                self.assertEqual(format_waiting(delta), expected)


# ---------------------------------------------------------------------------
# Список записей в админке
# ---------------------------------------------------------------------------


class AwaitingListTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="admin-list",
            email="admin-list@example.com",
            password="pass12345",
        )
        self.client.force_login(user)
        self.list_url = reverse("admin:catalog_booking_changelist")

        self.service = make_service()
        self.master = make_master()
        make_master_service(self.master, self.service)

    def book(self, name, hour, **kwargs):
        return make_booking(
            master=self.master,
            service=self.service,
            target_date=MONDAY,
            start_time=time(hour, 0),
            client_name=name,
            **kwargs,
        )

    def test_phone_is_a_call_link(self):
        self.book("Анна", 9, client_phone="+380990172668")

        response = self.client.get(self.list_url)

        self.assertContains(response, 'href="tel:+380990172668"')

    def test_filter_shows_count_of_awaiting_bookings(self):
        self.book("Первая", 9)
        self.book("Вторая", 10)
        self.book("Подтверждённая", 11, status=Booking.Status.CONFIRMED)

        response = self.client.get(self.list_url)

        self.assertContains(response, "Ждут звонка (2)")

    def test_filter_keeps_only_new_bookings(self):
        self.book("Новая", 9)
        self.book("Подтверждённая", 10, status=Booking.Status.CONFIRMED)

        response = self.client.get(self.list_url, {"awaiting": "yes"})

        self.assertContains(response, "Новая")
        self.assertNotContains(response, "Подтверждённая")

    def test_filter_puts_oldest_request_first(self):
        # По дате записи «Поздняя» стоит раньше, но оставлена позже всех.
        early_slot_late_request = self.book("Поздняя заявка", 9)
        late_slot_old_request = self.book("Давняя заявка", 17)

        Booking.objects.filter(pk=late_slot_old_request.pk).update(
            created_at=timezone.now() - timedelta(days=2),
        )
        Booking.objects.filter(pk=early_slot_late_request.pk).update(
            created_at=timezone.now() - timedelta(minutes=5),
        )

        response = self.client.get(self.list_url, {"awaiting": "yes"})
        content = response.content.decode()

        self.assertLess(
            content.index("Давняя заявка"),
            content.index("Поздняя заявка"),
        )

    def test_waiting_column_shows_how_long_a_new_booking_waits(self):
        waiting = self.book("Ждущая", 9)
        Booking.objects.filter(pk=waiting.pk).update(
            created_at=timezone.now() - timedelta(hours=3, minutes=10),
        )
        self.book("Подтверждённая", 10, status=Booking.Status.CONFIRMED)

        response = self.client.get(self.list_url)

        self.assertContains(response, "3 ч")
