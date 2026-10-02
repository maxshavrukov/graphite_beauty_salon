from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.category_list, name="category-list"),
    path("masters/", views.master_list, name="master-list"),
    path("masters/<slug:slug>/services/", views.master_services, name="master-services"),
    path(
        "masters/<slug:slug>/services/<slug:service_slug>/available-dates/",
        views.master_service_available_dates,
        name="master-service-available-dates",
    ),
    path(
        "masters/<slug:slug>/services/<slug:service_slug>/available-times/",
        views.master_service_available_times,
        name="master-service-available-times",
    ),
    path(
        "services/<slug:service_slug>/available-dates/",
        views.service_available_dates,
        name="service-available-dates",
    ),
    path(
        "services/<slug:service_slug>/available-times/",
        views.service_available_times,
        name="service-available-times",
    ),
    path(
        "services/<slug:service_slug>/available-masters/",
        views.service_available_masters,
        name="service-available-masters",
    ),
    path("bookings/", views.booking_create, name="booking-create"),
]
