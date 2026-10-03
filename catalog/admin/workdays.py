"""
Рабочие дни и отсутствия мастеров — технические страницы со списками.

Это временный вид: позже расписание будет заполняться специальной
формой и календарём. Пока здесь можно посмотреть и поправить записи.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import Absence, WorkDay


@admin.register(WorkDay)
class WorkDayAdmin(ModelAdmin):
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
