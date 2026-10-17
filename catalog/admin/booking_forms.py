"""
Формы записей в админке.

Новая запись создаётся только через create_booking (см. bookings.py),
а перед этим форма проверяет время теми же правилами, что и сайт.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from unfold.widgets import UnfoldAdminDateWidget, UnfoldAdminSelectWidget

from ..models import Booking, Master, Service
from ..phone import InvalidPhoneError, normalize_ua_phone
from ..services import (
    SlotUnavailableError,
    can_change_status,
    validate_booking_slot,
    validate_reschedule,
)
from .widgets import time_field


def clean_phone(value):
    """Номер клиента в едином формате или ошибка поля формы."""
    try:
        return normalize_ua_phone(value)
    except InvalidPhoneError as error:
        raise ValidationError(
            "Введите номер в формате 0991234567 или +380991234567.",
        ) from error


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

    def clean_client_phone(self):
        return clean_phone(self.cleaned_data["client_phone"])

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
    Форма существующей записи.

    Всегда можно поправить данные клиента и комментарий. Пока запись
    активна (новая или подтверждённая), можно ещё перенести её (другие
    мастер, услуга, дата, время) и сменить статус на допустимый. Это
    сценарий «клиенту перезвонили, договорились на другое время».

    Поля переноса (new_*) не привязаны к модели: форма только проверяет
    их, а менять запись должна reschedule_booking под блокировкой
    (см. BookingAdmin.save_model). Если поле пустое или не пришло,
    значит, оно не меняется.

    Закрытая запись (отменена, завершена, неявка) не переносится,
    и вернуть её в работу нельзя: это время могли занять.
    """

    MOVE_FIELDS = ("new_master", "new_service", "new_date", "new_start_time")

    new_master = forms.ModelChoiceField(
        label="Мастер",
        queryset=Master.objects.none(),
        required=False,
        widget=UnfoldAdminSelectWidget,
    )
    new_service = forms.ModelChoiceField(
        label="Услуга",
        queryset=Service.objects.none(),
        required=False,
        widget=UnfoldAdminSelectWidget,
    )
    new_date = forms.DateField(
        label="Дата",
        required=False,
        widget=UnfoldAdminDateWidget,
    )
    new_start_time = time_field("Время начала", required=False, step_minutes=15)

    class Meta:
        model = Booking
        fields = ("client_name", "client_phone", "status", "comment")
        labels = {
            "client_name": "Имя клиента",
            "client_phone": "Телефон клиента",
            "status": "Статус",
            "comment": "Комментарий",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        booking = self.instance
        current_status = booking.status

        # В списке статусов только текущий и допустимые переходы.
        allowed = Booking.ALLOWED_TRANSITIONS.get(current_status, ())
        status_field = self.fields["status"]
        if isinstance(status_field, forms.ChoiceField):
            status_field.choices = [
                (value, label)
                for value, label in Booking.Status.choices
                if value == current_status or value in allowed
            ]

        if booking.pk is None or current_status not in Booking.ACTIVE_STATUSES:
            for name in self.MOVE_FIELDS:
                del self.fields[name]
            return

        # Выбрать можно работающего мастера и действующую услугу, а также
        # тех, что уже в записи (даже если их потом отключили).
        master_field = self.fields["new_master"]
        if isinstance(master_field, forms.ModelChoiceField):
            master_field.queryset = Master.objects.filter(
                Q(is_active=True) | Q(pk=booking.master_id),
            )
            master_field.initial = booking.master_id

        service_field = self.fields["new_service"]
        if isinstance(service_field, forms.ModelChoiceField):
            service_field.queryset = Service.objects.filter(
                Q(is_active=True) | Q(pk=booking.service_id),
            )
            service_field.initial = booking.service_id

        self.fields["new_date"].initial = booking.date
        self.fields["new_start_time"].initial = booking.start_time

    def clean_client_phone(self):
        return clean_phone(self.cleaned_data["client_phone"])

    def clean_status(self):
        new_status = self.cleaned_data["status"]
        old_status = self.initial.get("status")

        if new_status == old_status:
            return new_status

        # Отменённую запись нельзя «оживить»: за это время уже мог
        # записаться другой клиент, а проверок при смене статуса нет.
        if (
            old_status not in Booking.ACTIVE_STATUSES
            and new_status in Booking.ACTIVE_STATUSES
        ):
            raise ValidationError(
                "Закрытую запись нельзя вернуть в работу: это время могли "
                "занять. Создайте новую запись."
            )

        if not can_change_status(old_status, new_status):
            raise ValidationError("Такая смена статуса не разрешена.")

        return new_status

    def get_move(self):
        """
        Что админ изменил в мастере, услуге, дате и времени.

        Словарь с ключами master / service / target_date / start_time,
        только для изменённых полей (подходит для reschedule_booking).
        Пустой словарь означает, что запись не переносят.
        """
        cleaned = getattr(self, "cleaned_data", None)

        if not cleaned or "new_master" not in self.fields:
            return {}

        booking = self.instance
        move = {}

        master = cleaned.get("new_master")
        if master and master.pk != booking.master_id:
            move["master"] = master

        service = cleaned.get("new_service")
        if service and service.pk != booking.service_id:
            move["service"] = service

        target_date = cleaned.get("new_date")
        if target_date and target_date != booking.date:
            move["target_date"] = target_date

        start_time = cleaned.get("new_start_time")
        if start_time and start_time != booking.start_time:
            move["start_time"] = start_time

        return move

    def clean(self):
        cleaned_data = super().clean()

        move = self.get_move()

        if not move:
            return cleaned_data

        new_status = cleaned_data.get("status")

        if new_status is not None and new_status not in Booking.ACTIVE_STATUSES:
            raise ValidationError(
                "Нельзя одновременно перенести запись и закрыть её. "
                "Сначала сохраните перенос, затем смените статус."
            )

        booking = self.instance

        try:
            validate_reschedule(
                booking,
                master=move.get("master", booking.master),
                service=move.get("service", booking.service),
                target_date=move.get("target_date", booking.date),
                start_time=move.get("start_time", booking.start_time),
            )
        except SlotUnavailableError as error:
            raise ValidationError(str(error)) from error

        return cleaned_data
