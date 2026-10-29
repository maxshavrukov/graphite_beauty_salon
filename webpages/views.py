from django.db.models import Prefetch
from django.views.generic import TemplateView

from catalog.models import Master, Service, ServiceCategory


def bookable_services():
    """Услуги, на которые клиент реально может записаться."""
    return Service.objects.filter(
        is_active=True,
        category__is_active=True,
        master_services__is_active=True,
        master_services__master__is_active=True,
    ).distinct()


def bookable_masters():
    """Мастера, которых можно показывать: активные и с хотя бы одной активной услугой."""
    return Master.objects.filter(
        is_active=True,
        master_services__is_active=True,
        master_services__service__is_active=True,
    ).distinct()


class HomeView(TemplateView):
    template_name = "webpages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        services = bookable_services()

        context["categories"] = (
            ServiceCategory.objects.filter(is_active=True, services__in=services)
            .distinct()
            .prefetch_related(
                Prefetch("services", queryset=services, to_attr="public_services"),
            )
        )
        context["masters"] = bookable_masters()
        return context


class BookingView(TemplateView):
    template_name = "webpages/booking.html"
