from django.contrib import admin
from .models import (
    Booking,
    Master,
    MasterService,
    ScheduleException,
    Service,
    ServiceCategory,
    TimeBlock,
    WorkingHours,
)


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "is_active",
        "sort_order",
    )
    list_editable = ("is_active", "sort_order")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Master)
class MasterAdmin(admin.ModelAdmin):
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

@admin.register(MasterService)
class MasterServiceAdmin(admin.ModelAdmin):
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

@admin.register(WorkingHours)
class WorkingHoursAdmin(admin.ModelAdmin):
    list_display = (
        "master",
        "weekday",
        "start_time",
        "end_time",
    )
    list_filter = ("master", "weekday")
    search_fields = ("master__name",)

@admin.register(ScheduleException)
class ScheduleExceptionAdmin(admin.ModelAdmin):
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
class TimeBlockAdmin(admin.ModelAdmin):
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
    
@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "start_time",
        "client_name",
        "client_phone",
        "master",
        "service",
        "price",
        "duration",
        "status",
        "source",
    )
    list_filter = (
        "status",
        "source",
        "master",
        "service",
        "date",
    )
    search_fields = (
        "client_name",
        "client_phone",
        "master__name",
        "service__name",
    )