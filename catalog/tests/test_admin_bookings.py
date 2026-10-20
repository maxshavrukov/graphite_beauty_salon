from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.admin import BookingChangeForm, BookingCreateForm
from catalog.models import Booking
from catalog.tests.factories import (
    make_booking,
    make_master,
    make_master_service,
    make_service,
)

TARGET_DATE = date(2026, 9, 7)


def create_data(master: Any, service: Any, **overrides: Any) -> dict[str, Any]:
    """Данные формы новой записи, как их шлёт браузер."""
    data = {
        "master": master.pk,
        "service": service.pk,
        "date": "2026-09-07",
        "start_time": "09:00:00",
        "client_name": "Иван",
        "client_phone": "+380000000000",
        "source": Booking.Source.ADMIN,
        "comment": "",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Формы
# ---------------------------------------------------------------------------


class BookingCreateFormTests(TestCase):
    def setUp(self) -> None:
        self.service = make_service()
        self.master = make_master()
        make_master_service(self.master, self.service, price=450, duration=30)

    def test_valid_for_free_time(self) -> None:
        form = BookingCreateForm(data=create_data(self.master, self.service))

        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_when_time_is_already_taken(self) -> None:
        make_booking(
            master=self.master,
            service=self.service,
            target_date=TARGET_DATE,
            start_time=time(9, 0),
            duration=30,
        )

        form = BookingCreateForm(data=create_data(self.master, self.service))

        self.assertFalse(form.is_valid())
        self.assertIn("Выбранное время уже занято.", form.non_field_errors())

    def test_invalid_when_master_does_not_offer_service(self) -> None:
        other_service = make_service()

        form = BookingCreateForm(data=create_data(self.master, other_service))

        self.assertFalse(form.is_valid())
        self.assertIn("Мастер не оказывает данную услугу.", form.non_field_errors())

    def test_online_source_is_not_allowed(self) -> None:
        form = BookingCreateForm(
            data=create_data(self.master, self.service, source=Booking.Source.ONLINE),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("source", form.errors)

    def test_inactive_master_cannot_be_chosen(self) -> None:
        self.master.is_active = False
        self.master.save()

        form = BookingCreateForm(data=create_data(self.master, self.service))

        self.assertFalse(form.is_valid())
        self.assertIn("master", form.errors)


class BookingChangeFormTests(TestCase):
    def make_form(self, booking: Booking, **overrides: Any) -> BookingChangeForm:
        data = {
            "client_name": booking.client_name,
            "client_phone": booking.client_phone,
            "status": booking.status,
            "comment": booking.comment,
        }
        data.update(overrides)
        return BookingChangeForm(data=data, instance=booking)

    def test_active_booking_can_be_cancelled(self) -> None:
        booking = make_booking(target_date=TARGET_DATE, start_time=time(9, 0))

        form = self.make_form(booking, status=Booking.Status.CANCELLED)

        self.assertTrue(form.is_valid(), form.errors)

    def test_cancelled_booking_cannot_be_returned_to_work(self) -> None:
        booking = make_booking(
            target_date=TARGET_DATE,
            start_time=time(9, 0),
            status=Booking.Status.CANCELLED,
        )

        form = self.make_form(booking, status=Booking.Status.CONFIRMED)

        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_cancelled_booking_can_still_get_a_comment(self) -> None:
        booking = make_booking(
            target_date=TARGET_DATE,
            start_time=time(9, 0),
            status=Booking.Status.CANCELLED,
        )

        form = self.make_form(booking, comment="Клиент перезвонил")

        self.assertTrue(form.is_valid(), form.errors)


# ---------------------------------------------------------------------------
# Админка целиком (через тестовый браузер)
# ---------------------------------------------------------------------------


class BookingAdminTests(TestCase):
    def setUp(self) -> None:
        user_model: Any = get_user_model()
        user = user_model.objects.create_superuser(
            username="admin-test",
            email="admin-test@example.com",
            password="pass12345",
        )
        self.client.force_login(user)

        self.service = make_service()
        self.master = make_master()
        make_master_service(
            self.master, self.service, price=Decimal("450.00"), duration=30,
        )
        self.add_url = reverse("admin:catalog_booking_add")
        self.list_url = reverse("admin:catalog_booking_changelist")

    def run_action(self, action: str, *bookings: Booking) -> Any:
        return self.client.post(
            self.list_url,
            {
                "action": action,
                "_selected_action": [booking.pk for booking in bookings],
            },
        )

    # --- создание ---------------------------------------------------------

    def test_add_creates_booking_with_price_and_duration_from_price_list(self) -> None:
        response = self.client.post(
            self.add_url,
            create_data(self.master, self.service),
        )

        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get()
        self.assertEqual(booking.price, Decimal("450.00"))
        self.assertEqual(booking.duration, 30)
        self.assertEqual(booking.status, Booking.Status.NEW)
        self.assertEqual(booking.source, Booking.Source.ADMIN)
        self.assertEqual(booking.client_name, "Иван")

    def test_add_does_not_create_booking_for_taken_time(self) -> None:
        make_booking(
            master=self.master,
            service=self.service,
            target_date=TARGET_DATE,
            start_time=time(9, 0),
            duration=30,
        )

        response = self.client.post(
            self.add_url,
            create_data(self.master, self.service),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Booking.objects.count(), 1)

    # --- правка существующей записи --------------------------------------

    def test_change_updates_status_but_not_readonly_fields(self) -> None:
        booking = make_booking(
            master=self.master,
            service=self.service,
            target_date=TARGET_DATE,
            start_time=time(9, 0),
        )

        response = self.client.post(
            reverse("admin:catalog_booking_change", args=[booking.pk]),
            {
                "client_name": "Пётр",
                "client_phone": booking.client_phone,
                "status": Booking.Status.CONFIRMED,
                "comment": "Позвонить заранее",
                # Попытка подменить дату: поле закрыто для правки.
                "date": "2027-01-01",
            },
        )

        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(booking.client_name, "Пётр")
        self.assertEqual(booking.date, TARGET_DATE)

    def test_change_cannot_return_cancelled_booking_to_work(self) -> None:
        booking = make_booking(
            master=self.master,
            service=self.service,
            target_date=TARGET_DATE,
            start_time=time(9, 0),
            status=Booking.Status.CANCELLED,
        )

        response = self.client.post(
            reverse("admin:catalog_booking_change", args=[booking.pk]),
            {
                "client_name": booking.client_name,
                "client_phone": booking.client_phone,
                "status": Booking.Status.CONFIRMED,
                "comment": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    # --- действия над выбранными записями ---------------------------------

    def test_confirm_action_confirms_only_new_bookings(self) -> None:
        new = make_booking(
            master=self.master, service=self.service,
            target_date=TARGET_DATE, start_time=time(9, 0),
        )
        cancelled = make_booking(
            master=self.master, service=self.service,
            target_date=TARGET_DATE, start_time=time(10, 0),
            status=Booking.Status.CANCELLED,
        )

        response = self.run_action("confirm_bookings", new, cancelled)

        self.assertEqual(response.status_code, 302)
        new.refresh_from_db()
        cancelled.refresh_from_db()
        self.assertEqual(new.status, Booking.Status.CONFIRMED)
        self.assertEqual(cancelled.status, Booking.Status.CANCELLED)

    def test_cancel_action_skips_completed_bookings(self) -> None:
        confirmed = make_booking(
            master=self.master, service=self.service,
            target_date=TARGET_DATE, start_time=time(9, 0),
            status=Booking.Status.CONFIRMED,
        )
        completed = make_booking(
            master=self.master, service=self.service,
            target_date=TARGET_DATE, start_time=time(10, 0),
            status=Booking.Status.COMPLETED,
        )

        self.run_action("cancel_bookings", confirmed, completed)

        confirmed.refresh_from_db()
        completed.refresh_from_db()
        self.assertEqual(confirmed.status, Booking.Status.CANCELLED)
        self.assertEqual(completed.status, Booking.Status.COMPLETED)

    def test_no_show_action_marks_confirmed_booking(self) -> None:
        booking = make_booking(
            master=self.master, service=self.service,
            target_date=TARGET_DATE, start_time=time(9, 0),
            status=Booking.Status.CONFIRMED,
        )

        self.run_action("mark_no_show", booking)

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.NO_SHOW)

    def test_complete_action_marks_confirmed_booking(self) -> None:
        booking = make_booking(
            master=self.master, service=self.service,
            target_date=TARGET_DATE, start_time=time(9, 0),
            status=Booking.Status.CONFIRMED,
        )

        self.run_action("complete_bookings", booking)

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)

    # --- быстрый фильтр по дню --------------------------------------------

    def test_day_filter_today_shows_only_todays_bookings(self) -> None:
        today = timezone.localdate()
        make_booking(
            master=self.master, service=self.service,
            target_date=today, start_time=time(9, 0),
            client_name="Сегодняшний",
        )
        make_booking(
            master=self.master, service=self.service,
            target_date=today + timedelta(days=1), start_time=time(9, 0),
            client_name="Завтрашний",
        )

        response = self.client.get(self.list_url, {"when": "today"})

        self.assertContains(response, "Сегодняшний")
        self.assertNotContains(response, "Завтрашний")
