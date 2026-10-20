"""Админка мастеров: карточка мастера на вкладках и его прайс."""

from django import forms
from django.contrib import admin
from django.db import transaction
from unfold.admin import ModelAdmin, TabularInline

from ..models import Absence, Master, MasterService, TimeBlock
from .widgets import time_field


# ---------------------------------------------------------------------------
# Форма для вкладки «Занятое время»
# ---------------------------------------------------------------------------


class TimeBlockInlineForm(forms.ModelForm):
    start_time = time_field("С")
    end_time = time_field("До")

    class Meta:
        model = TimeBlock
        fields = ("date", "start_time", "end_time", "reason")
        labels = {"date": "Дата", "reason": "Причина"}


# ---------------------------------------------------------------------------
# Вкладки внутри карточки мастера
# ---------------------------------------------------------------------------


class MasterServiceInline(TabularInline):
    model = MasterService
    extra = 1
    tab = True
    fields = ("service", "price", "duration", "is_active")
    verbose_name = "Услуга и цена"
    verbose_name_plural = "Услуги и цены"


class AbsenceInline(TabularInline):
    model = Absence
    extra = 0
    tab = True
    fields = ("kind", "start_date", "end_date", "comment")
    verbose_name = "Отсутствие"
    verbose_name_plural = "Отпуск и отсутствия"


class TimeBlockInline(TabularInline):
    model = TimeBlock
    form = TimeBlockInlineForm
    extra = 0
    tab = True
    verbose_name = "Занятое время"
    verbose_name_plural = "Занятое время"


# ---------------------------------------------------------------------------
# Сам мастер и его прайс
# ---------------------------------------------------------------------------


@admin.register(Master)
class MasterAdmin(ModelAdmin):
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
    inlines = [
        MasterServiceInline,
        AbsenceInline,
        TimeBlockInline,
    ]

    def save_formset(self, request, form, formset, change):
        # Booking creation locks the master before validating its schedule.
        # Lock the same master and repeat model validation immediately before
        # saving Absence/TimeBlock rows, so a booking created during form
        # validation cannot silently overlap a new absence/block.
        if formset.model not in (Absence, TimeBlock):
            return super().save_formset(request, form, formset, change)

        with transaction.atomic():
            Master.objects.select_for_update().get(pk=form.instance.pk)
            instances = formset.save(commit=False)

            for deleted_object in formset.deleted_objects:
                deleted_object.delete()

            for instance in instances:
                instance.full_clean()
                instance.save()

            formset.save_m2m()


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
