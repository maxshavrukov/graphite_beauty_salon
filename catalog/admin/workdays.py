"""
Рабочие дни и отсутствия мастеров — технические страницы со списками.

Это временный вид: позже расписание будет заполняться специальной
формой и календарём. Пока здесь можно посмотреть и поправить записи.
"""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from unfold.admin import ModelAdmin

from ..models import Absence, Master, WorkDay
from ..services.schedule_editor import remove_work_days


@admin.register(WorkDay)
class WorkDayAdmin(ModelAdmin):
    actions = ("remove_selected_work_days",)

    list_display = (
        "master",
        "date",
        "start_time",
        "end_time",
        "break_start",
        "break_end",
    )
    list_filter = ("master", "date")
    search_fields = ("master__name",)

    def save_model(self, request, obj, form, change):
        assert isinstance(obj, WorkDay)
        with transaction.atomic():
            master_ids = {obj.master_id}
            if obj.pk is not None:
                original = WorkDay.objects.filter(pk=obj.pk).values_list(
                    "master_id", flat=True,
                ).first()
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
