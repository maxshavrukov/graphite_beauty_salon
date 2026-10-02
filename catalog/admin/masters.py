"""Админка мастеров: карточка мастера на вкладках и его прайс."""

from django import forms
from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from ..models import Master, MasterService, ScheduleException, TimeBlock
from .master_forms import WEEK_FIELDS, MasterAdminForm, MasterBaseForm
from .widgets import time_field


# Формы для блоков внутри карточки мастера


class ScheduleExceptionInlineForm(forms.ModelForm):
    start_time = time_field("Начало", required=False)
    end_time = time_field("Конец", required=False)

    class Meta:
        model = ScheduleException
        fields = ("date", "is_closed", "start_time", "end_time", "reason")
        labels = {
            "date": "Дата",
            "is_closed": "Выходной",
            "reason": "Причина",
        }


class TimeBlockInlineForm(forms.ModelForm):
    start_time = time_field("С")
    end_time = time_field("До")

    class Meta:
        model = TimeBlock
        fields = ("date", "start_time", "end_time", "reason")
        labels = {"date": "Дата", "reason": "Причина"}


# Блоки (вкладки) внутри карточки мастера


class MasterServiceInline(TabularInline):
    model = MasterService
    extra = 1
    tab = True
    fields = ("service", "price", "duration", "is_active")
    verbose_name = "Услуга и цена"
    verbose_name_plural = "Услуги и цены"


class ScheduleExceptionInline(TabularInline):
    model = ScheduleException
    form = ScheduleExceptionInlineForm
    extra = 0
    tab = True
    verbose_name = "Особый день"
    verbose_name_plural = "Особые дни"


class TimeBlockInline(TabularInline):
    model = TimeBlock
    form = TimeBlockInlineForm
    extra = 0
    tab = True
    verbose_name = "Занятое время"
    verbose_name_plural = "Занятое время"


# Сам мастер


@admin.register(Master)
class MasterAdmin(ModelAdmin):
    form = MasterAdminForm
    list_display = (
        "name",
        "slug",
        "is_active",
        "sort_order",
    )
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "bio")
    prepopulated_fields = {"slug": ("name",)}

    fieldsets = (
        (
            None,
            {"fields": ("name", "slug", "is_active", "sort_order")},
        ),
        (
            "Обычная неделя",
            {
                "description": (
                    "Отметьте рабочие дни и выберите время. Перерыв "
                    "необязателен. Дни без галочки — выходные."
                ),
                "fields": WEEK_FIELDS,
            },
        ),
        (
            "О мастере",
            {"fields": ("photo", "bio")},
        ),
    )

    inlines = [
        MasterServiceInline,
        ScheduleExceptionInline,
        TimeBlockInline,
    ]

    def save_related(self, request, form, formsets, change):
        # К этому моменту мастер уже сохранён и у него есть id,
        # поэтому можно записывать его недельный график.
        super().save_related(request, form, formsets, change)

        if isinstance(form, MasterBaseForm):
            form.save_week()


@admin.register(MasterService)
class MasterServiceAdmin(ModelAdmin):
    list_display = (
        "master",
        "service",
        "price",
        "duration",
        "is_active",
    )
    list_editable = ("price", "duration", "is_active")
    list_filter = ("master", "service", "is_active")
    search_fields = (
        "master__name",
        "service__name",
    )
