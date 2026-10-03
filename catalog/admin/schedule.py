"""
Общий список занятого времени всех мастеров (обеды, личные дела).

Править блокировки удобнее в карточке мастера, а этот список нужен,
чтобы увидеть картину по всему салону.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from ..models import TimeBlock


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
