"""Админка записей: список, фильтры, действия и создание записи."""

from datetime import timedelta

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils import timezone
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from ..models import Booking
from ..services import SlotUnavailableError, create_booking
from .booking_forms import (
    ACTIVE_BOOKING_STATUSES,
    BookingChangeForm,
    BookingCreateForm,
)


class BookingDayFilter(admin.SimpleListFilter):
    """Быстрый фильтр по дню: сегодня, завтра, неделя, прошедшие."""

    title = "Когда"
    parameter_name = "when"

    def lookups(self, request, model_admin):
        return (
            ("today", "Сегодня"),
            ("tomorrow", "Завтра"),
            ("week", "Ближайшие 7 дней"),
            ("past", "Прошедшие"),
        )

    def queryset(self, request, queryset):
        today = timezone.localdate()

        if self.value() == "today":
            return queryset.filter(date=today)

        if self.value() == "tomorrow":
            return queryset.filter(date=today + timedelta(days=1))

        if self.value() == "week":
            return queryset.filter(
                date__range=(today, today + timedelta(days=6)),
            )

        if self.value() == "past":
            return queryset.filter(date__lt=today)

        return queryset


# Цвет значка статуса в списке. Ключ — подпись статуса, как её видит админ.
STATUS_COLORS: dict[str, str] = {
    str(Booking.Status.NEW.label): "warning",
    str(Booking.Status.CONFIRMED.label): "success",
    str(Booking.Status.COMPLETED.label): "info",
    str(Booking.Status.CANCELLED.label): "danger",
    str(Booking.Status.NO_SHOW.label): "danger",
}


@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    list_display = (
        "date",
        "start_time",
        "client_name",
        "client_phone",
        "master",
        "service",
        "price",
        "duration",
        "status_badge",
        "source",
    )
    list_filter = (
        BookingDayFilter,
        "status",
        "master",
        "service",
        "source",
        "date",
    )
    list_select_related = ("master", "service")
    search_fields = (
        "client_name",
        "client_phone",
        "master__name",
        "service__name",
    )
    actions = [
        "confirm_bookings",
        "complete_bookings",
        "mark_no_show",
        "cancel_bookings",
    ]

    # --- Формы: новая запись и существующая выглядят по-разному ----------

    def get_form(self, request, obj=None, change=False, **kwargs):
        kwargs["form"] = BookingCreateForm if obj is None else BookingChangeForm
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                (None, {"fields": ("master", "service", "date", "start_time")}),
                ("Клиент", {"fields": ("client_name", "client_phone", "comment")}),
                ("Дополнительно", {"fields": ("source",)}),
            )

        return (
            (
                "Запись",
                {
                    "fields": (
                        "master",
                        "service",
                        "date",
                        "start_time",
                        "price",
                        "duration",
                    ),
                },
            ),
            ("Клиент", {"fields": ("client_name", "client_phone")}),
            (
                "Статус",
                {
                    "fields": (
                        "status",
                        "source",
                        "comment",
                        "created_at",
                        "updated_at",
                    ),
                },
            ),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()

        return (
            "master",
            "service",
            "date",
            "start_time",
            "price",
            "duration",
            "source",
            "created_at",
            "updated_at",
        )

    # --- Создание записи идёт только через create_booking ----------------

    def save_model(self, request, obj, form, change):
        # isinstance — не только защита, но и подсказка для редактора:
        # дальше он знает, что obj это Booking и у него есть master, date...
        if change or not isinstance(obj, Booking):
            super().save_model(request, obj, form, change)
            return

        created = create_booking(
            master=obj.master,
            service=obj.service,
            target_date=obj.date,
            start_time=obj.start_time,
            client_name=obj.client_name,
            client_phone=obj.client_phone,
            source=obj.source,
            comment=obj.comment,
        )

        # Дальше админка продолжает работать с obj (журнал действий,
        # переход на другую страницу), поэтому переносим в него всё, что
        # создал create_booking: id, цену, длительность, время создания.
        for field in created._meta.concrete_fields:
            setattr(obj, field.attname, getattr(created, field.attname))

        obj._state.adding = False
        obj._state.db = created._state.db

    def add_view(self, request, form_url="", extra_context=None):
        try:
            return super().add_view(request, form_url, extra_context)
        except SlotUnavailableError as error:
            # Редкий случай: время заняли за доли секунды между проверкой
            # формы и сохранением. Ничего не записалось, просто сообщаем.
            self.message_user(
                request,
                f"Запись не создана: {error}",
                level=messages.ERROR,
            )
            return HttpResponseRedirect(request.get_full_path())

    # --- Вид списка ------------------------------------------------------

    @display(
        description="Статус",
        ordering="status",
        label=STATUS_COLORS,
    )
    def status_badge(self, obj):
        return obj.get_status_display()

    # --- Действия над выбранными записями --------------------------------

    def _change_status(self, request, queryset, allowed_from, new_status, done_text):
        """
        Меняет статус только у записей, для которых такой переход разумен,
        и сообщает, сколько записей изменено и сколько пропущено.
        """
        total = queryset.count()
        updated = queryset.filter(status__in=allowed_from).update(
            status=new_status,
            updated_at=timezone.now(),
        )
        skipped = total - updated

        if updated:
            self.message_user(
                request,
                f"{done_text}: {updated}.",
                level=messages.SUCCESS,
            )

        if skipped:
            self.message_user(
                request,
                f"Пропущено записей (для них это действие не подходит): {skipped}.",
                level=messages.WARNING,
            )

    @action(description="Подтвердить")
    def confirm_bookings(self, request, queryset):
        self._change_status(
            request,
            queryset,
            (Booking.Status.NEW,),
            Booking.Status.CONFIRMED,
            "Подтверждено записей",
        )

    @action(description="Отметить «Завершена»")
    def complete_bookings(self, request, queryset):
        self._change_status(
            request,
            queryset,
            ACTIVE_BOOKING_STATUSES,
            Booking.Status.COMPLETED,
            "Завершено записей",
        )

    @action(description="Отметить «Не пришёл»")
    def mark_no_show(self, request, queryset):
        self._change_status(
            request,
            queryset,
            ACTIVE_BOOKING_STATUSES,
            Booking.Status.NO_SHOW,
            "Отмечено неявок",
        )

    @action(description="Отменить")
    def cancel_bookings(self, request, queryset):
        self._change_status(
            request,
            queryset,
            ACTIVE_BOOKING_STATUSES,
            Booking.Status.CANCELLED,
            "Отменено записей",
        )
