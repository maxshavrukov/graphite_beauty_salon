"""
Отдельные списки расписания: рабочее время, особые дни и занятое время
всех мастеров сразу. Править график удобнее в карточке мастера, а эти
списки нужны, чтобы увидеть картину по всему салону.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import ScheduleException, TimeBlock, WorkingHours


@admin.register(WorkingHours)
class WorkingHoursAdmin(ModelAdmin):
    list_display = (
        "master",
        "weekday",
        "start_time",
        "end_time",
    )
    list_filter = ("master", "weekday")
    search_fields = ("master__name",)


@admin.register(ScheduleException)
class ScheduleExceptionAdmin(ModelAdmin):
    list_display = (
        "master",
        "date",
        "is_closed",
        "start_time",
        "end_time",
        "reason",
    )
    list_filter = (
        "master",
        "is_closed",
        "date",
    )
    search_fields = (
        "master__name",
        "reason",
    )


@admin.register(TimeBlock)
class TimeBlockAdmin(ModelAdmin):
    list_display = (
        "master",
        "date",
        "start_time",
        "end_time",
        "reason",
    )
    list_filter = (
        "master",
        "date",
    )
    search_fields = (
        "master__name",
        "reason",
    )
