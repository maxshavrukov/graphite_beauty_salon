"""
Формы записей в админке.

Новая запись создаётся только через create_booking (см. bookings.py),
а перед этим форма проверяет время теми же правилами, что и сайт.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from unfold.widgets import UnfoldAdminSelectWidget

from ..models import Booking, Master, Service
from ..services import SlotUnavailableError, validate_booking_slot
from .widgets import time_field


# Статусы, при которых запись занимает время мастера.
ACTIVE_BOOKING_STATUSES = (Booking.Status.NEW, Booking.Status.CONFIRMED)


class BookingCreateForm(forms.ModelForm):
    """
    Форма новой записи в админке (по телефону или лично).

    Цену и длительность админ не вводит: они берутся из прайса мастера
    автоматически. Время проверяется теми же правилами, что и у клиента
    на сайте, поэтому поставить двух клиентов на одно время нельзя.
    """

    start_time = time_field("Время начала", step_minutes=15)
    source = forms.ChoiceField(
        label="Как поступила запись",
        choices=[
            (Booking.Source.PHONE, "Телефон"),
            (Booking.Source.ADMIN, "Администратор"),
        ],
        initial=Booking.Source.ADMIN,
        widget=UnfoldAdminSelectWidget,
    )

    class Meta:
        model = Booking
        fields = (
            "master",
            "service",
            "date",
            "start_time",
            "client_name",
            "client_phone",
            "source",
            "comment",
        )
        labels = {
            "master": "Мастер",
            "service": "Услуга",
            "date": "Дата",
            "client_name": "Имя клиента",
            "client_phone": "Телефон клиента",
            "comment": "Комментарий",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Записать можно только к работающему мастеру на действующую услугу.
        master_field = self.fields["master"]
        if isinstance(master_field, forms.ModelChoiceField):
            master_field.queryset = Master.objects.filter(is_active=True)

        service_field = self.fields["service"]
        if isinstance(service_field, forms.ModelChoiceField):
            service_field.queryset = Service.objects.filter(is_active=True)

        self.fields["date"].initial = timezone.localdate()

    def clean(self):
        cleaned_data = super().clean()

        master = cleaned_data.get("master")
        service = cleaned_data.get("service")
        target_date = cleaned_data.get("date")
        start_time = cleaned_data.get("start_time")
        source = cleaned_data.get("source")

        if master and service and target_date and start_time and source:
            try:
                validate_booking_slot(
                    master,
                    service,
                    target_date,
                    start_time,
                    source,
                )
            except SlotUnavailableError as error:
                raise ValidationError(str(error)) from error

        return cleaned_data


class BookingChangeForm(forms.ModelForm):
    """
    Форма существующей записи: можно поправить данные клиента, статус
    и комментарий. Мастер, услуга, дата и время закрыты для правки —
    чтобы перенести запись, её отменяют и создают новую (с проверкой).
    """

    class Meta:
        model = Booking
        fields = ("client_name", "client_phone", "status", "comment")
        labels = {
            "client_name": "Имя клиента",
            "client_phone": "Телефон клиента",
            "status": "Статус",
            "comment": "Комментарий",
        }

    def clean_status(self):
        new_status = self.cleaned_data["status"]
        old_status = self.initial.get("status")

        # Отменённую запись нельзя «оживить»: за это время уже мог
        # записаться другой клиент, а проверок при смене статуса нет.
        if (
            old_status not in ACTIVE_BOOKING_STATUSES
            and new_status in ACTIVE_BOOKING_STATUSES
        ):
            raise ValidationError(
                "Закрытую запись нельзя вернуть в работу: это время могли "
                "занять. Создайте новую запись."
            )

        return new_status
