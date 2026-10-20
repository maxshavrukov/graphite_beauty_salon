"""
Изменение существующей записи: смена статуса, перенос, журнал, админка.

Сценарий из жизни: клиент оставил заявку, админ ему перезвонил, договорился
на другое время, поправил запись в админке и подтвердил.
"""

from datetime import date, time
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.admin import BookingChangeForm
from catalog.models import Booking, BookingEvent, TimeBlock
from catalog.services import (
    BookingStateError,
    SlotUnavailableError,
    change_booking_status,
    create_booking,
    reschedule_booking,
    validate_booking_slot,
)
from catalog.tests.factories import (
    make_absence,
    make_booking,
    make_master,
    make_master_service,
    make_service,
    make_work_day,
)

MONDAY = date(2026, 9, 7)
TUESDAY = date(2026, 9, 8)


def make_user(username="staff"):
    user_model: Any = get_user_model()
    return user_model.objects.create_superuser(
        username=username,
        email=f"{username}@example.com",
        password="pass12345",
    )


class BookingTestCase(TestCase):
    """Мастер с рабочим днём и услугой на 30 минут за 450."""

    def setUp(self):
        self.service = make_service()
        self.master = make_master()
        self.master_service = make_master_service(
            self.master, self.service, price=Decimal("450.00"), duration=30,
        )
        make_work_day(self.master, MONDAY, time(9, 0), time(18, 0))

    def book(self, start_time=time(10, 0), **kwargs):
        kwargs.setdefault("master", self.master)
        kwargs.setdefault("service", self.service)
        kwargs.setdefault("target_date", MONDAY)
        kwargs.setdefault("duration", 30)
        kwargs.setdefault("price", Decimal("450.00"))
        # Уже в том виде, в котором номер хранится: иначе форма админки
        # «нормализует» его и пишет в журнал лишнее событие.
        kwargs.setdefault("client_phone", "+380000000000")
        return make_booking(start_time=start_time, **kwargs)


# ---------------------------------------------------------------------------
# Таблица переходов
# ---------------------------------------------------------------------------


class TransitionTableTests(TestCase):
    def test_every_status_has_a_rule(self):
        # Появится новый статус: тест заставит решить, куда из него можно.
        self.assertEqual(set(Booking.ALLOWED_TRANSITIONS), set(Booking.Status))

    def test_closed_status_never_returns_to_work(self):
        for status, targets in Booking.ALLOWED_TRANSITIONS.items():
            if status in Booking.ACTIVE_STATUSES:
                continue

            with self.subTest(status=status):
                for target in targets:
                    self.assertNotIn(target, Booking.ACTIVE_STATUSES)


# ---------------------------------------------------------------------------
# change_booking_status
# ---------------------------------------------------------------------------


class ChangeBookingStatusTests(BookingTestCase):
    def test_confirms_new_booking_and_writes_journal(self):
        booking = self.book()
        user = make_user()

        result = change_booking_status(
            booking, Booking.Status.CONFIRMED, actor=user,
        )

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(result.status, Booking.Status.CONFIRMED)

        event = booking.events.get()
        self.assertEqual(event.kind, BookingEvent.Kind.STATUS)
        self.assertEqual(event.from_status, Booking.Status.NEW)
        self.assertEqual(event.to_status, Booking.Status.CONFIRMED)
        self.assertEqual(event.actor, user)

    def test_accepts_booking_id(self):
        booking = self.book()

        change_booking_status(booking.pk, Booking.Status.CANCELLED)

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_forbidden_transitions_change_nothing(self):
        forbidden = [
            (Booking.Status.NEW, Booking.Status.COMPLETED),
            (Booking.Status.NEW, Booking.Status.NO_SHOW),
            (Booking.Status.NEW, Booking.Status.NEW),
            (Booking.Status.CONFIRMED, Booking.Status.NEW),
            (Booking.Status.CONFIRMED, Booking.Status.CONFIRMED),
            (Booking.Status.CANCELLED, Booking.Status.CONFIRMED),
            (Booking.Status.COMPLETED, Booking.Status.CANCELLED),
            (Booking.Status.NO_SHOW, Booking.Status.CONFIRMED),
        ]

        for hour, (old, new) in enumerate(forbidden, start=9):
            with self.subTest(old=old, new=new):
                booking = self.book(start_time=time(hour, 0), status=old)

                with self.assertRaises(BookingStateError):
                    change_booking_status(booking, new)

                booking.refresh_from_db()
                self.assertEqual(booking.status, old)
                self.assertEqual(booking.events.count(), 0)

    def test_completed_and_no_show_can_be_corrected(self):
        completed = self.book(status=Booking.Status.COMPLETED)
        no_show = self.book(start_time=time(11, 0), status=Booking.Status.NO_SHOW)

        change_booking_status(completed, Booking.Status.NO_SHOW)
        change_booking_status(no_show, Booking.Status.COMPLETED)

        completed.refresh_from_db()
        no_show.refresh_from_db()
        self.assertEqual(completed.status, Booking.Status.NO_SHOW)
        self.assertEqual(no_show.status, Booking.Status.COMPLETED)

    def test_cancelling_frees_the_time(self):
        booking = self.book(status=Booking.Status.CONFIRMED)

        with self.assertRaises(SlotUnavailableError):
            validate_booking_slot(
                self.master, self.service, MONDAY, time(10, 0),
                Booking.Source.ADMIN,
            )

        change_booking_status(booking, Booking.Status.CANCELLED)

        validate_booking_slot(
            self.master, self.service, MONDAY, time(10, 0),
            Booking.Source.ADMIN,
        )


# ---------------------------------------------------------------------------
# validate_booking_slot: новые параметры для переноса
# ---------------------------------------------------------------------------


class ValidateSlotForRescheduleTests(BookingTestCase):
    def test_booking_conflicts_with_itself_without_exclude(self):
        booking = self.book()

        with self.assertRaises(SlotUnavailableError):
            validate_booking_slot(
                self.master, self.service, MONDAY, time(10, 0),
                Booking.Source.ADMIN,
            )

        validate_booking_slot(
            self.master, self.service, MONDAY, time(10, 0),
            Booking.Source.ADMIN,
            exclude_booking_id=booking.pk,
        )

    def test_exclude_does_not_hide_other_bookings(self):
        booking = self.book()
        self.book(start_time=time(11, 0))

        with self.assertRaises(SlotUnavailableError):
            validate_booking_slot(
                self.master, self.service, MONDAY, time(11, 0),
                Booking.Source.ADMIN,
                exclude_booking_id=booking.pk,
            )

    def test_duration_override_is_used_for_overlap(self):
        self.book(start_time=time(11, 0))

        # По прайсу 30 минут: 10:30–11:00 свободно. Но для записи на
        # 60 минут то же время заходит на чужую запись в 11:00.
        validate_booking_slot(
            self.master, self.service, MONDAY, time(10, 30),
            Booking.Source.ADMIN,
        )

        with self.assertRaises(SlotUnavailableError):
            validate_booking_slot(
                self.master, self.service, MONDAY, time(10, 30),
                Booking.Source.ADMIN,
                duration_minutes=60,
            )

    def test_online_source_does_not_accept_reschedule_arguments(self):
        with self.assertRaises(ValueError):
            validate_booking_slot(
                self.master, self.service, MONDAY, time(10, 0),
                Booking.Source.ONLINE,
                exclude_booking_id=1,
            )


# ---------------------------------------------------------------------------
# reschedule_booking
# ---------------------------------------------------------------------------


class RescheduleBookingTests(BookingTestCase):
    def test_moves_to_free_time_and_writes_journal(self):
        booking = self.book()
        user = make_user()

        reschedule_booking(booking, start_time=time(12, 0), actor=user)

        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(12, 0))
        self.assertEqual(booking.date, MONDAY)

        event = booking.events.get()
        self.assertEqual(event.kind, BookingEvent.Kind.RESCHEDULED)
        self.assertEqual(event.actor, user)
        self.assertIn("10:00", event.details)
        self.assertIn("12:00", event.details)

    def test_status_is_not_changed_by_reschedule(self):
        new = self.book()
        confirmed = self.book(start_time=time(14, 0), status=Booking.Status.CONFIRMED)

        reschedule_booking(new, start_time=time(11, 0))
        reschedule_booking(confirmed, start_time=time(15, 0))

        new.refresh_from_db()
        confirmed.refresh_from_db()
        self.assertEqual(new.status, Booking.Status.NEW)
        self.assertEqual(confirmed.status, Booking.Status.CONFIRMED)

    def test_can_shift_onto_its_own_old_time(self):
        booking = self.book()

        reschedule_booking(booking, start_time=time(10, 15))

        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(10, 15))

    def test_changes_date(self):
        booking = self.book()
        make_work_day(self.master, TUESDAY)

        reschedule_booking(booking, target_date=TUESDAY)

        booking.refresh_from_db()
        self.assertEqual(booking.date, TUESDAY)
        self.assertEqual(booking.start_time, time(10, 0))

    def test_admin_may_move_outside_work_days(self):
        # Даже онлайн-запись админ вправе поставить на неотмеченный день.
        booking = self.book(source=Booking.Source.ONLINE)

        reschedule_booking(booking, target_date=TUESDAY)

        booking.refresh_from_db()
        self.assertEqual(booking.date, TUESDAY)

    def test_keeps_agreed_price_and_duration(self):
        booking = self.book()
        other = self.book(start_time=time(11, 0))

        # Прайс мастера поменяли уже после записи клиента.
        self.master_service.price = Decimal("900.00")
        self.master_service.duration = 60
        self.master_service.save()

        # 10:30–11:00 по обещанным клиенту 30 минутам не задевает запись
        # в 11:00, а по новым 60 минутам задевало бы.
        reschedule_booking(booking, start_time=time(10, 30))

        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(10, 30))
        self.assertEqual(booking.price, Decimal("450.00"))
        self.assertEqual(booking.duration, 30)
        other.refresh_from_db()
        self.assertEqual(other.start_time, time(11, 0))

    def test_other_booking_blocks_and_nothing_changes(self):
        booking = self.book()
        self.book(start_time=time(12, 0))

        with self.assertRaises(SlotUnavailableError):
            reschedule_booking(booking, start_time=time(12, 0))

        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(10, 0))
        self.assertEqual(booking.events.count(), 0)

    def test_cancelled_booking_does_not_block(self):
        booking = self.book()
        self.book(start_time=time(12, 0), status=Booking.Status.CANCELLED)

        reschedule_booking(booking, start_time=time(12, 0))

        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(12, 0))

    def test_time_block_prevents_move(self):
        booking = self.book()
        TimeBlock.objects.create(
            master=self.master,
            date=MONDAY,
            start_time=time(12, 0),
            end_time=time(13, 0),
        )

        with self.assertRaises(SlotUnavailableError):
            reschedule_booking(booking, start_time=time(12, 0))

    def test_absence_prevents_move(self):
        booking = self.book()
        make_absence(self.master, TUESDAY)

        with self.assertRaises(SlotUnavailableError):
            reschedule_booking(booking, target_date=TUESDAY)

        booking.refresh_from_db()
        self.assertEqual(booking.date, MONDAY)

    def test_change_master_takes_price_and_duration_from_new_master(self):
        booking = self.book()
        other_master = make_master()
        make_master_service(
            other_master, self.service, price=Decimal("700.00"), duration=45,
        )

        reschedule_booking(booking, master=other_master)

        booking.refresh_from_db()
        self.assertEqual(booking.master, other_master)
        self.assertEqual(booking.price, Decimal("700.00"))
        self.assertEqual(booking.duration, 45)
        self.assertIn(other_master.name, booking.events.get().details)

    def test_master_without_the_service_is_rejected(self):
        booking = self.book()
        other_master = make_master()

        with self.assertRaises(SlotUnavailableError):
            reschedule_booking(booking, master=other_master)

        booking.refresh_from_db()
        self.assertEqual(booking.master, self.master)

    def test_closed_booking_cannot_be_changed(self):
        for status in (
            Booking.Status.CANCELLED,
            Booking.Status.COMPLETED,
            Booking.Status.NO_SHOW,
        ):
            with self.subTest(status=status):
                booking = self.book(start_time=time(16, 0), status=status)

                with self.assertRaises(BookingStateError):
                    reschedule_booking(booking, start_time=time(17, 0))

    def test_can_reschedule_existing_pair_after_it_is_deactivated(self):
        booking = self.book()
        self.master.is_active = False
        self.master.save(update_fields=["is_active"])
        self.master_service.is_active = False
        self.master_service.save(update_fields=["is_active"])
        self.service.is_active = False
        self.service.save(update_fields=["is_active"])

        reschedule_booking(booking, start_time=time(12, 0))

        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(12, 0))
        self.assertEqual(booking.price, Decimal("450.00"))
        self.assertEqual(booking.duration, 30)

    def test_nothing_to_change_writes_no_journal(self):
        booking = self.book()

        result = reschedule_booking(booking, start_time=time(10, 0))

        self.assertEqual(result.pk, booking.pk)
        self.assertEqual(booking.events.count(), 0)


# ---------------------------------------------------------------------------
# Журнал создания записи
# ---------------------------------------------------------------------------


class CreateBookingJournalTests(BookingTestCase):
    def test_creation_is_written_to_journal(self):
        user = make_user()

        booking = create_booking(
            self.master,
            self.service,
            MONDAY,
            time(10, 0),
            "Анна",
            "+380501234567",
            source=Booking.Source.PHONE,
            actor=user,
        )

        event = booking.events.get()
        self.assertEqual(event.kind, BookingEvent.Kind.CREATED)
        self.assertEqual(event.actor, user)
        self.assertEqual(event.to_status, Booking.Status.NEW)


# ---------------------------------------------------------------------------
# Форма записи в админке
# ---------------------------------------------------------------------------


class BookingChangeFormMoveTests(BookingTestCase):
    def make_form(self, booking, **overrides):
        data = {
            "client_name": booking.client_name,
            "client_phone": booking.client_phone,
            "status": booking.status,
            "comment": booking.comment,
        }
        data.update(overrides)
        return BookingChangeForm(data=data, instance=booking)

    def test_status_choices_show_only_allowed_transitions(self):
        booking = self.book()

        form = BookingChangeForm(instance=booking)

        status_field: Any = form.fields["status"]
        values = {value for value, _ in status_field.choices}
        self.assertEqual(
            values,
            {Booking.Status.NEW, Booking.Status.CONFIRMED, Booking.Status.CANCELLED},
        )

    def test_without_move_fields_booking_is_not_moved(self):
        booking = self.book()

        form = self.make_form(booking)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.get_move(), {})

    def test_move_fields_are_reported(self):
        booking = self.book()

        form = self.make_form(booking, new_start_time="12:00:00")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.get_move(), {"start_time": time(12, 0)})

    def test_move_to_taken_time_is_invalid(self):
        booking = self.book()
        self.book(start_time=time(12, 0))

        form = self.make_form(booking, new_start_time="12:00:00")

        self.assertFalse(form.is_valid())
        self.assertIn("Выбранное время уже занято.", form.non_field_errors())

    def test_cannot_move_and_cancel_at_once(self):
        booking = self.book()

        form = self.make_form(
            booking,
            new_start_time="12:00:00",
            status=Booking.Status.CANCELLED,
        )

        self.assertFalse(form.is_valid())

    def test_closed_booking_has_no_move_fields(self):
        booking = self.book(status=Booking.Status.CANCELLED)

        form = BookingChangeForm(instance=booking)

        for name in BookingChangeForm.MOVE_FIELDS:
            self.assertNotIn(name, form.fields)


# ---------------------------------------------------------------------------
# Админка целиком
# ---------------------------------------------------------------------------


class BookingAdminChangeTests(BookingTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user("admin-changes")
        self.client.force_login(self.user)
        self.list_url = reverse("admin:catalog_booking_changelist")

    def change_url(self, booking):
        return reverse("admin:catalog_booking_change", args=[booking.pk])

    def post_change(self, booking, **overrides):
        data = {
            "client_name": booking.client_name,
            "client_phone": booking.client_phone,
            "status": booking.status,
            "comment": booking.comment,
            "new_master": booking.master_id,
            "new_service": booking.service_id,
            "new_date": booking.date.isoformat(),
            "new_start_time": booking.start_time.strftime("%H:%M:%S"),
        }
        data.update(overrides)
        return self.client.post(self.change_url(booking), data)

    def test_change_page_opens_for_active_booking(self):
        booking = self.book()

        response = self.client.get(self.change_url(booking))

        self.assertEqual(response.status_code, 200)

    def test_change_page_opens_for_closed_booking(self):
        booking = self.book(status=Booking.Status.CANCELLED)

        response = self.client.get(self.change_url(booking))

        self.assertEqual(response.status_code, 200)

    def test_untouched_form_changes_nothing(self):
        booking = self.book()

        response = self.post_change(booking)

        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(10, 0))
        self.assertEqual(booking.events.count(), 0)

    def test_admin_moves_booking_to_new_time(self):
        booking = self.book()

        response = self.post_change(booking, new_start_time="12:00:00")

        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(12, 0))
        self.assertEqual(booking.status, Booking.Status.NEW)

        event = booking.events.get()
        self.assertEqual(event.kind, BookingEvent.Kind.RESCHEDULED)
        self.assertEqual(event.actor, self.user)

    def test_admin_client_data_changes_are_audited(self):
        booking = self.book()

        response = self.post_change(booking, client_name="Новое имя")

        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.client_name, "Новое имя")
        event = booking.events.get()
        self.assertEqual(event.kind, BookingEvent.Kind.CLIENT_UPDATED)
        self.assertIn("Тестовый клиент", event.details)
        self.assertIn("Новое имя", event.details)
        self.assertEqual(event.actor, self.user)

    def test_admin_moves_and_confirms_in_one_save(self):
        booking = self.book()

        response = self.post_change(
            booking,
            new_start_time="12:00:00",
            status=Booking.Status.CONFIRMED,
        )

        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(12, 0))
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)
        self.assertEqual(
            list(booking.events.values_list("kind", flat=True)),
            [BookingEvent.Kind.RESCHEDULED, BookingEvent.Kind.STATUS],
        )

    def test_move_to_taken_time_is_rejected_and_page_shows_why(self):
        booking = self.book()
        self.book(start_time=time(12, 0))

        response = self.post_change(booking, new_start_time="12:00:00")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Выбранное время уже занято.")
        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(10, 0))

    def test_cannot_move_and_cancel_together(self):
        booking = self.book()

        response = self.post_change(
            booking,
            new_start_time="12:00:00",
            status=Booking.Status.CANCELLED,
        )

        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(10, 0))
        self.assertEqual(booking.status, Booking.Status.NEW)

    def test_forbidden_status_jump_is_rejected(self):
        booking = self.book()

        response = self.post_change(booking, status=Booking.Status.COMPLETED)

        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.NEW)

    def test_closed_booking_ignores_move_fields(self):
        booking = self.book(status=Booking.Status.CANCELLED)

        response = self.post_change(booking, new_start_time="12:00:00")

        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.start_time, time(10, 0))

    def test_history_is_shown_on_the_page(self):
        booking = self.book()
        change_booking_status(booking, Booking.Status.CONFIRMED, actor=self.user)

        response = self.client.get(self.change_url(booking))

        self.assertContains(response, "Новая → Подтверждена")

    def test_confirm_action_writes_journal_with_actor(self):
        booking = self.book()

        self.client.post(
            self.list_url,
            {"action": "confirm_bookings", "_selected_action": [booking.pk]},
        )

        event = booking.events.get()
        self.assertEqual(event.to_status, Booking.Status.CONFIRMED)
        self.assertEqual(event.actor, self.user)

    def test_complete_action_skips_unconfirmed_booking(self):
        new = self.book()

        self.client.post(
            self.list_url,
            {"action": "complete_bookings", "_selected_action": [new.pk]},
        )

        new.refresh_from_db()
        self.assertEqual(new.status, Booking.Status.NEW)
        self.assertEqual(new.events.count(), 0)

    def test_add_via_admin_writes_created_event_with_actor(self):
        response = self.client.post(
            reverse("admin:catalog_booking_add"),
            {
                "master": self.master.pk,
                "service": self.service.pk,
                "date": MONDAY.isoformat(),
                "start_time": "13:00:00",
                "client_name": "Иван",
                "client_phone": "+380000000000",
                "source": Booking.Source.PHONE,
                "comment": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        event = BookingEvent.objects.get()
        self.assertEqual(event.kind, BookingEvent.Kind.CREATED)
        self.assertEqual(event.actor, self.user)
