from django.db.models import Count, Max, Min, Prefetch, Q
from django.views.generic import DetailView, TemplateView

from catalog.models import Master, MasterService, Service, ServiceCategory


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
        master_services__service__category__is_active=True,
    ).distinct()


def priced_services():
    """
    Услуги, на которые можно записаться, с границами цены и длительности
    по активным мастерам. Услуги без активных мастеров отсеиваются.
    """
    offer = Q(
        master_services__is_active=True,
        master_services__master__is_active=True,
    )
    return (
        Service.objects.filter(is_active=True, category__is_active=True)
        .select_related("category")
        .annotate(
            offers=Count("master_services", filter=offer),
            price_min=Min("master_services__price", filter=offer),
            price_max=Max("master_services__price", filter=offer),
            duration_min=Min("master_services__duration", filter=offer),
            duration_max=Max("master_services__duration", filter=offer),
        )
        .filter(offers__gt=0)
        .order_by(
            "category__sort_order",
            "category__name",
            "category_id",
            "sort_order",
            "name",
        )
    )


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


class ServicesView(TemplateView):
    template_name = "webpages/services.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["services"] = priced_services()
        return context


class MasterDetailView(DetailView):
    template_name = "webpages/master_detail.html"
    context_object_name = "master"

    def get_queryset(self):
        # Тот же отбор, что и на главной: неактивные мастера и мастера
        # без услуг дают 404.
        return bookable_masters()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["offers"] = (
            MasterService.objects.filter(
                master=self.object,
                is_active=True,
                service__is_active=True,
                service__category__is_active=True,
            )
            .select_related("service", "service__category")
            .order_by(
                "service__category__sort_order",
                "service__category__name",
                "service__category_id",
                "service__sort_order",
                "service__name",
            )
        )
        return context
