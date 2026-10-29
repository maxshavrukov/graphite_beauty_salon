"""
Рабочие дни и отсутствия мастеров — технические страницы со списками.

Основной способ заполнять расписание — страница «Расписание» (календарь,
см. schedule_calendar.py). Этот список нужен, чтобы точечно посмотреть или
поправить отдельный день.
"""

from functools import partial

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import path
from unfold.admin import ModelAdmin

from ..models import Absence, Master, WorkDay
from ..services.schedule_editor import remove_work_days
from .schedule_calendar import schedule_view
from .widgets import time_field

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


class WorkDayForm(forms.ModelForm):
    """Время выбирается из списка с шагом сетки записи, а не часами-пикером."""

    start_time = time_field("Начало работы")
    end_time = time_field("Конец работы")
    break_start = time_field("Перерыв с", required=False)
    break_end = time_field("Перерыв до", required=False)

    class Meta:
        model = WorkDay
        fields = (
            "master",
            "date",
            "start_time",
            "end_time",
            "break_start",
            "break_end",
        )


@admin.register(WorkDay)
class WorkDayAdmin(ModelAdmin):
    form = WorkDayForm
    actions = ("remove_selected_work_days",)

    list_display = (
        "master",
        "day",
        "hours",
        "break_hours",
    )
    list_filter = ("master", "date")
    search_fields = ("master__name",)

    def get_urls(self):
        # Страница-календарь расписания. Свои адреса идут раньше
        # стандартных, иначе «calendar/» примется за id рабочего дня.
        # Адрес намеренно не начинается с адреса списка мастеров, чтобы
        # в меню Unfold не подсвечивались сразу два пункта.
        custom = [
            path(
                "calendar/",
                self.admin_site.admin_view(partial(schedule_view, self)),
                name="catalog_workday_schedule",
            ),
        ]
        return custom + super().get_urls()

    @admin.display(description="Дата", ordering="date")
    def day(self, obj):
        return f"{obj.date:%d.%m.%Y}, {WEEKDAYS[obj.date.weekday()]}"

    @admin.display(description="Работает")
    def hours(self, obj):
        return f"{obj.start_time:%H:%M}–{obj.end_time:%H:%M}"

    @admin.display(description="Перерыв")
    def break_hours(self, obj):
        if obj.break_start is None or obj.break_end is None:
            return "—"
        return f"{obj.break_start:%H:%M}–{obj.break_end:%H:%M}"

    def save_model(self, request, obj, form, change):
        assert isinstance(obj, WorkDay)
        with transaction.atomic():
            master_ids = {obj.master_id}
            if obj.pk is not None:
                original = (
                    WorkDay.objects.filter(pk=obj.pk)
                    .values_list(
                        "master_id",
                        flat=True,
                    )
                    .first()
                )
                if original is not None:
                    master_ids.add(original)
            # При возможной смене мастера блокируем исходного и целевого
            # владельца рабочего дня в одном порядке.
            for master_id in sorted(master_ids):
                Master.objects.select_for_update().get(pk=master_id)
            # Model.clean повторно проверяет, не выталкивает ли новый график
            # существующие онлайн-записи за рабочие интервалы.
            obj.full_clean()
            super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        # Удаление рабочего дня может скрыть подтверждённую онлайн-запись из
        # календаря доступности. Вместо стандартного удаления используется
        # действие, которое проверяет конфликты и сообщает понятную ошибку.
        return False

    @admin.action(description="Удалить выбранные рабочие дни")
    def remove_selected_work_days(self, request, queryset):
        rows = list(queryset.select_related("master").order_by("master_id", "date"))
        grouped = {}
        masters = {}
        for row in rows:
            grouped.setdefault(row.master_id, []).append(row.date)
            masters[row.master_id] = row.master

        try:
            with transaction.atomic():
                removed = 0
                for master_id in sorted(grouped):
                    removed += remove_work_days(masters[master_id], grouped[master_id])
        except ValidationError as error:
            self.message_user(
                request,
                "; ".join(error.messages),
                level=messages.ERROR,
            )
            return

        self.message_user(
            request,
            f"Удалено рабочих дней: {removed}.",
            level=messages.SUCCESS,
        )


@admin.register(Absence)
class AbsenceAdmin(ModelAdmin):
    list_display = (
        "master",
        "kind",
        "start_date",
        "end_date",
        "comment",
    )
    list_filter = ("master", "kind")
    search_fields = ("master__name", "comment")

    def save_model(self, request, obj, form, change):
        assert isinstance(obj, Absence)
        with transaction.atomic():
            Master.objects.select_for_update().get(pk=obj.master_id)
            obj.full_clean()
            super().save_model(request, obj, form, change)
