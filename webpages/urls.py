from django.urls import path

from . import views

app_name = "webpages"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("booking/", views.BookingView.as_view(), name="booking"),
    path("services/", views.ServicesView.as_view(), name="services"),
    path("masters/<slug:slug>/", views.MasterDetailView.as_view(), name="master"),
]
