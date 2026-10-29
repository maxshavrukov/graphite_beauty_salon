from django.urls import path

from . import views

app_name = "webpages"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("booking/", views.BookingView.as_view(), name="booking"),
]
