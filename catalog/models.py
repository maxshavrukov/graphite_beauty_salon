from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import models

if TYPE_CHECKING:
    from django_stubs_ext.db.models.manager import RelatedManager

# Create your models here.

class ServiceCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    if TYPE_CHECKING:
        services: "RelatedManager[Service]"

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Категория услуг"
        verbose_name_plural = "Категории услуг"

    def __str__(self):
        return self.name

class Service(models.Model):
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="services",
    )
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    if TYPE_CHECKING:
        master_services: "RelatedManager[MasterService]"
        bookings: "RelatedManager[Booking]"

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"

    def __str__(self):
        return self.name

class Master(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    photo = models.ImageField(upload_to="masters/", blank=True)
    bio = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    if TYPE_CHECKING:
        master_services: "RelatedManager[MasterService]"
        working_hours: "RelatedManager[WorkingHours]"
        schedule_exceptions: "RelatedManager[ScheduleException]"
        time_blocks: "RelatedManager[TimeBlock]"
        bookings: "RelatedManager[Booking]"

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Мастер"
        verbose_name_plural = "Мастера"

    def __str__(self):
        return self.name

class MasterService(models.Model):
    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="master_services",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="master_services",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    duration = models.PositiveIntegerField(
        help_text="Плановая продолжительность услуги в минутах.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["master", "service"],
                name="unique_master_service",
            ),
        ]
        verbose_name = "Услуга мастера"
        verbose_name_plural = "Услуги мастеров"

    def __str__(self):
        return f"{self.master} — {self.service}"

class WorkingHours(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Понедельник"
        TUESDAY = 1, "Вторник"
        WEDNESDAY = 2, "Среда"
        THURSDAY = 3, "Четверг"
        FRIDAY = 4, "Пятница"
        SATURDAY = 5, "Суббота"
        SUNDAY = 6, "Воскресенье"

    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="working_hours",
    )
    weekday = models.PositiveSmallIntegerField(
        choices=Weekday.choices,
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    if TYPE_CHECKING:
        # Django создаёт этот метод динамически из-за choices=
        # у поля weekday. mypy-плагин django-stubs видит это
        # автоматически, а Pylance/Pyright — нет, поэтому здесь
        # даём ему подсказку вручную.
        def get_weekday_display(self) -> str: ...

    class Meta:
        ordering = ["weekday", "start_time"]
        verbose_name = "Рабочее время"
        verbose_name_plural = "Рабочее время"

    def __str__(self):
        return (
            f"{self.master} — "
            f"{self.get_weekday_display()} "
            f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
        )

class ScheduleException(models.Model):
    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="schedule_exceptions",
    )
    date = models.DateField()
    is_closed = models.BooleanField(default=False)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["master", "date"],
                name="unique_master_schedule_exception",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        is_closed=True,
                        start_time__isnull=True,
                        end_time__isnull=True,
                    )
                    | models.Q(
                        is_closed=False,
                        start_time__isnull=False,
                        end_time__isnull=False,
                    )
                ),
                name="schedule_exception_time_consistency",
            ),
        ]
        ordering = ["date"]
        verbose_name = "Исключение из расписания"
        verbose_name_plural = "Исключения из расписания"

    def clean(self):
        if self.is_closed:
            if self.start_time is not None or self.end_time is not None:
                raise ValidationError(
                    "Для закрытого дня время начала и окончания "
                    "должно быть пустым."
                )
        else:
            if self.start_time is None or self.end_time is None:
                raise ValidationError(
                    "Для рабочего дня необходимо указать время начала "
                    "и окончания."
                )

            if self.start_time >= self.end_time:
                raise ValidationError(
                    "Время окончания должно быть позже времени начала."
                )

    def __str__(self):
        if self.is_closed:
            return f"{self.master} — {self.date} — выходной"

        return (
            f"{self.master} — {self.date} — "
            f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
        )

class TimeBlock(models.Model):
    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="time_blocks",
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name = "Блокировка времени"
        verbose_name_plural = "Блокировки времени"

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError(
                "Время окончания должно быть позже времени начала."
            )

    def __str__(self):
        return (
            f"{self.master} — {self.date} — "
            f"{self.start_time:%H:%M}–{self.end_time:%H:%M}"
        )

class Booking(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "Новая"
        CONFIRMED = "CONFIRMED", "Подтверждена"
        CANCELLED = "CANCELLED", "Отменена"
        COMPLETED = "COMPLETED", "Завершена"

    class Source(models.TextChoices):
        ONLINE = "ONLINE", "Онлайн"
        PHONE = "PHONE", "Телефон"
        ADMIN = "ADMIN", "Администратор"

    master = models.ForeignKey(
        Master,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    date = models.DateField()
    start_time = models.TimeField()

    client_name = models.CharField(max_length=100)
    client_phone = models.CharField(max_length=30)

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )
    duration = models.PositiveIntegerField(
        help_text="Плановая продолжительность услуги в минутах.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.ONLINE,
    )

    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name = "Запись"
        verbose_name_plural = "Записи"

    def __str__(self):
        return (
            f"{self.date} {self.start_time:%H:%M} — "
            f"{self.client_name} — {self.master}"
        )
