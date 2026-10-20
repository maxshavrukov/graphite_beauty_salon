"""
Общий список занятого времени всех мастеров (обеды, личные дела).

Править блокировки удобнее в карточке мастера, а этот список нужен,
чтобы увидеть картину по всему салону.
"""

from django.contrib import admin
from django.db import transaction
from unfold.admin import ModelAdmin

from ..models import Master, TimeBlock


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

    def save_model(self, request, obj, form, change):
        assert isinstance(obj, TimeBlock)
        with transaction.atomic():
            Master.objects.select_for_update().get(pk=obj.master_id)
            # Повторная проверка после блокировки мастера; форма могла быть
            # заполнена до того, как другой запрос создал запись клиента.
            obj.full_clean()
            super().save_model(request, obj, form, change)
