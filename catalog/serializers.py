import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .models import Booking, Master, MasterService, Service, ServiceCategory
from .services import create_booking


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["slug", "name", "description"]


class ServiceCategorySerializer(serializers.ModelSerializer):
    # Обычный related-менеджер category.services отдал бы вообще
    # все услуги, включая неактивные — фильтруем руками.
    services = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = ["slug", "name", "services"]

    def get_services(self, category):
        active_services = category.services.filter(
            is_active=True,
        ).order_by("sort_order", "name")

        return ServiceSerializer(active_services, many=True).data


class MasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Master
        fields = ["slug", "name", "photo", "bio"]


class MasterServiceSerializer(serializers.ModelSerializer):
    # Клиенту нужна сама услуга (имя, slug), а не служебный id
    # связи MasterService — разворачиваем вложенным сериализатором.
    service = ServiceSerializer()

    class Meta:
        model = MasterService
        fields = ["service", "price", "duration"]


class AvailableMasterSerializer(serializers.Serializer):
    """
    Не привязан к модели напрямую: сериализует словари вида
    {"master": <Master>, "price": Decimal(...)}, которые отдаёт
    get_available_masters_for_slot — а не саму модель MasterService.
    """
    master = MasterSerializer()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)


class BookingCreateSerializer(serializers.Serializer):
    """
    Входные данные для POST /api/bookings/.

    master и service приходят как slug. Источник записи (source)
    и статус здесь намеренно отсутствуют: их выставляет сервер,
    клиент повлиять на них не может.
    """

    master = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Master.objects.filter(is_active=True),
    )
    service = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Service.objects.filter(is_active=True),
    )
    date = serializers.DateField()
    start_time = serializers.TimeField(input_formats=["%H:%M"])
    client_name = serializers.CharField(max_length=100)
    client_phone = serializers.CharField(max_length=30)

    def validate_date(self, value):
        today = timezone.localdate()
        max_date = today + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD)

        if not (today <= value <= max_date):
            raise serializers.ValidationError(
                "Дата вне доступного окна записи.",
            )

        return value

    def validate_client_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Укажите имя.")

        return value

    def validate_client_phone(self, value):
        # Оставляем только цифры и ведущий "+", чтобы "+38 (050) 123-45-67"
        # и "380501234567" не превращались в разные строки в базе.
        has_plus = value.strip().startswith("+")
        digits = re.sub(r"\D", "", value)

        if not (10 <= len(digits) <= 15):
            raise serializers.ValidationError(
                "Укажите корректный номер телефона.",
            )

        return ("+" if has_plus else "") + digits

    def validate(self, attrs):
        # Пара мастер+услуга должна существовать: иначе это ошибка
        # запроса (400), а не "слот занят" (409).
        if not MasterService.objects.filter(
            master=attrs["master"],
            service=attrs["service"],
            is_active=True,
        ).exists():
            raise serializers.ValidationError(
                "Этот мастер не оказывает выбранную услугу.",
            )

        return attrs

    def create(self, validated_data):
        """
        serializer.save() вызывает этот метод. Может бросить
        SlotUnavailableError — вьюха превращает её в ответ 409.
        """
        return create_booking(
            master=validated_data["master"],
            service=validated_data["service"],
            target_date=validated_data["date"],
            start_time=validated_data["start_time"],
            client_name=validated_data["client_name"],
            client_phone=validated_data["client_phone"],
            source=Booking.Source.ONLINE,
        )


class BookingSerializer(serializers.ModelSerializer):
    """Ответ клиенту после создания записи."""

    master = serializers.CharField(source="master.name")
    service = serializers.CharField(source="service.name")

    class Meta:
        model = Booking
        fields = [
            "id",
            "master",
            "service",
            "date",
            "start_time",
            "price",
            "duration",
            "status",
        ]
