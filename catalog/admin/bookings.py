"""
Админка записей: список, фильтры, действия, создание и изменение записи.

Любое изменение существующей записи (статус, перенос) идёт через сервисы
change_booking_status и reschedule_booking: они проверяют правила, блокируют
запись от гонки и пишут журнал. Напрямую в таблицу админка не пишет.
"""

from datetime import timedelta

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin
from unfold.decorators import action, display

from ..models import Booking, BookingEvent
from ..services import (
    BookingStateError,
    SlotUnavailableError,
    change_booking_status,
    create_booking,
    reschedule_booking,
)
from .booking_forms import BookingChangeForm, BookingCreateForm


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


class BookingAwaitingFilter(admin.SimpleListFilter):
    """
    «Ждут звонка»: новые заявки, которые админ ещё не подтвердил.

    В названии сразу видно, сколько их. При включённом фильтре самые
    старые заявки идут первыми (см. BookingAdmin.get_ordering), чтобы
    никто не ждал звонка дольше остальных.
    """

    title = "Подтверждение"
    parameter_name = "awaiting"

    def lookups(self, request, model_admin):
        count = (
            model_admin.get_queryset(request)
            .filter(status=Booking.Status.NEW)
            .count()
        )
        return (("yes", f"Ждут звонка ({count})"),)

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(status=Booking.Status.NEW)

        return queryset


def format_waiting(delta: timedelta) -> str:
    """Сколько ждёт заявка: «5 мин», «3 ч», «2 д»."""
    minutes = int(delta.total_seconds() // 60)

    if minutes < 1:
        return "только что"

    if minutes < 60:
        return f"{minutes} мин"

    if minutes < 24 * 60:
        return f"{minutes // 60} ч"

    return f"{minutes // (24 * 60)} д"


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
        "phone_link",
        "master",
        "service",
        "price",
        "duration",
        "status_badge",
        "waiting",
        "source",
    )
    list_filter = (
        BookingAwaitingFilter,
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

    def get_ordering(self, request):
        # «Ждут звонка»: сначала те, кто оставил заявку раньше всех.
        if request.GET.get("awaiting") == "yes":
            return ("created_at", "id")

        return super().get_ordering(request)

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

        # Активную запись можно перенести (поля new_*), закрытую только
        # смотреть: мастер, услуга, дата и время показываются текстом.
        if obj.status in Booking.ACTIVE_STATUSES:
            slot_fields = (
                "new_master",
                "new_service",
                "new_date",
                "new_start_time",
            )
        else:
            slot_fields = ("master", "service", "date", "start_time")

        return (
            ("Запись", {"fields": (*slot_fields, "price", "duration")}),
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
            ("История", {"fields": ("history",)}),
        )

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()

        readonly = [
            "price",
            "duration",
            "source",
            "created_at",
            "updated_at",
            "history",
        ]

        if obj.status not in Booking.ACTIVE_STATUSES:
            readonly += ["master", "service", "date", "start_time"]

        return tuple(readonly)

    # --- Создание записи идёт только через create_booking ----------------

    def save_model(self, request, obj, form, change):
        # isinstance — не только защита, но и подсказка для редактора:
        # дальше он знает, что obj это Booking и у него есть master, date...
        if not isinstance(obj, Booking):
            super().save_model(request, obj, form, change)
            return

        if change:
            self._save_changes(request, obj, form)
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
            actor=request.user,
        )

        self._copy_saved_fields(obj, created)

    @staticmethod
    def _copy_saved_fields(obj, saved):
        # Дальше админка продолжает работать с obj (журнал действий,
        # переход на другую страницу), поэтому переносим в него всё, что
        # записали сервисы: id, цену, длительность, время изменения.
        for field in saved._meta.concrete_fields:
            setattr(obj, field.attname, getattr(saved, field.attname))

        obj._state.adding = False
        obj._state.db = saved._state.db

    def _save_changes(self, request, obj, form):
        """
        Сохраняет правку существующей записи: сначала перенос, потом данные
        клиента, потом статус. Всё внутри транзакции страницы: если что-то
        не прошло, не сохраняется ничего.

        Форма уже изменила obj по полям клиента и статуса, но в базу ничего
        не записано. Поэтому берём свежую запись из базы и меняем её сами:
        иначе перенос и смена статуса обошли бы проверки и блокировки.
        """
        booking = Booking.objects.get(pk=obj.pk)
        cleaned = form.cleaned_data

        move = form.get_move()
        if move:
            booking = reschedule_booking(
                booking,
                actor=request.user,
                **move,
            )

        changed_fields = []
        for field in ("client_name", "client_phone", "comment"):
            if getattr(booking, field) != cleaned[field]:
                setattr(booking, field, cleaned[field])
                changed_fields.append(field)

        if changed_fields:
            booking.save(update_fields=[*changed_fields, "updated_at"])

        new_status = cleaned["status"]
        if new_status != booking.status:
            booking = change_booking_status(
                booking,
                new_status,
                actor=request.user,
            )

        self._copy_saved_fields(obj, booking)

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

    def change_view(self, request, object_id, form_url="", extra_context=None):
        try:
            return super().change_view(
                request,
                object_id,
                form_url,
                extra_context,
            )
        except (SlotUnavailableError, BookingStateError) as error:
            # Редкий случай: пока форма была открыта, запись изменил кто-то
            # другой или время заняли. Страница откатывается целиком.
            self.message_user(
                request,
                f"Изменения не сохранены: {error}",
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

    @display(description="Телефон", ordering="client_phone")
    def phone_link(self, obj):
        # Ссылка tel: на телефоне или в программе для звонков набирает номер
        # одним нажатием.
        return format_html(
            '<a href="tel:{}">{}</a>',
            obj.client_phone,
            obj.client_phone,
        )

    @display(description="Ждёт", ordering="created_at")
    def waiting(self, obj):
        if obj.status != Booking.Status.NEW:
            return "—"

        return format_waiting(timezone.now() - obj.created_at)

    @display(description="История")
    def history(self, obj):
        events = list(obj.events.select_related("actor"))

        if not events:
            return "—"

        def line(event):
            moment = timezone.localtime(event.created_at)
            who = event.actor.get_username() if event.actor else "клиент / система"

            if event.kind == BookingEvent.Kind.STATUS:
                what = (
                    f"Статус: {Booking.Status(event.from_status).label} → "
                    f"{Booking.Status(event.to_status).label}"
                )
            elif event.kind == BookingEvent.Kind.CREATED:
                what = "Запись создана"
            else:
                what = f"Изменена: {event.details}"

            return (f"{moment:%d.%m.%Y %H:%M} — {what} ({who})",)

        return format_html_join(
            mark_safe("<br>"),
            "{}",
            (line(event) for event in events),
        )

    # --- Действия над выбранными записями --------------------------------

    def _change_status(self, request, queryset, new_status, done_text):
        """
        Меняет статус у выбранных записей через сервис и сообщает, сколько
        записей изменено и сколько пропущено (для них такой переход не
        разрешён правилами Booking.ALLOWED_TRANSITIONS).
        """
        updated = 0
        skipped = 0

        for booking in queryset:
            try:
                change_booking_status(
                    booking,
                    new_status,
                    actor=request.user,
                )
            except BookingStateError:
                skipped += 1
            else:
                updated += 1

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
            Booking.Status.CONFIRMED,
            "Подтверждено записей",
        )

    @action(description="Отметить «Завершена»")
    def complete_bookings(self, request, queryset):
        self._change_status(
            request,
            queryset,
            Booking.Status.COMPLETED,
            "Завершено записей",
        )

    @action(description="Отметить «Не пришёл»")
    def mark_no_show(self, request, queryset):
        self._change_status(
            request,
            queryset,
            Booking.Status.NO_SHOW,
            "Отмечено неявок",
        )

    @action(description="Отменить")
    def cancel_bookings(self, request, queryset):
        self._change_status(
            request,
            queryset,
            Booking.Status.CANCELLED,
            "Отменено записей",
        )
