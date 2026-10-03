from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import models

# Create your models here.


class ServiceCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    if TYPE_CHECKING:
        services: Any

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
        master_services: Any
        bookings: Any

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
        master_services: Any
        time_blocks: Any
        bookings: Any
        work_days: Any
        absences: Any

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
        NO_SHOW = "NO_SHOW", "Не пришёл"

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

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name = "Запись"
        verbose_name_plural = "Записи"

    def __str__(self):
        return (
            f"{self.date} {self.start_time:%H:%M} — "
            f"{self.client_name} — {self.master}"
        )


# ---------------------------------------------------------------------------
# Расписание мастера: рабочие дни и отсутствия
# ---------------------------------------------------------------------------


class WorkDay(models.Model):
    """
    Рабочий день мастера: конкретная дата, время работы и необязательный
    перерыв. Нет записи на дату — значит, в этот день мастер не отмечен
    (клиенты времени не видят, но админ может вписать запись вручную).
    """

    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="work_days",
        verbose_name="Мастер",
    )
    date = models.DateField("Дата")
    start_time = models.TimeField("Начало работы")
    end_time = models.TimeField("Конец работы")
    break_start = models.TimeField("Перерыв с", null=True, blank=True)
    break_end = models.TimeField("Перерыв до", null=True, blank=True)

    if TYPE_CHECKING:
        # Django создаёт master_id динамически из-за ForeignKey master.
        master_id: int

    class Meta:
        ordering = ["date"]
        verbose_name = "Рабочий день"
        verbose_name_plural = "Рабочие дни"
        constraints = [
            models.UniqueConstraint(
                fields=["master", "date"],
                name="unique_work_day_per_master_date",
            ),
            models.CheckConstraint(
                condition=models.Q(start_time__lt=models.F("end_time")),
                name="work_day_start_before_end",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(break_start__isnull=True, break_end__isnull=True)
                    | models.Q(
                        break_start__isnull=False,
                        break_end__isnull=False,
                        break_start__gt=models.F("start_time"),
                        break_start__lt=models.F("break_end"),
                        break_end__lt=models.F("end_time"),
                    )
                ),
                name="work_day_break_is_valid",
            ),
        ]

    def __str__(self):
        return f"{self.master} — {self.date}"

    def get_intervals(self):
        """
        Рабочие интервалы дня: один без перерыва, два с перерывом
        (перерыв — это «дырка» между ними).
        """
        if self.break_start is None or self.break_end is None:
            return [(self.start_time, self.end_time)]

        return [
            (self.start_time, self.break_start),
            (self.break_end, self.end_time),
        ]

    def clean(self):
        if self.start_time is None or self.end_time is None:
            return

        if self.start_time >= self.end_time:
            raise ValidationError(
                "Время окончания должно быть позже времени начала."
            )

        if (self.break_start is None) != (self.break_end is None):
            raise ValidationError(
                "Для перерыва укажите и начало, и конец "
                "(или оставьте оба поля пустыми)."
            )

        if self.break_start is not None and self.break_end is not None:
            if self.break_start >= self.break_end:
                raise ValidationError(
                    "Конец перерыва должен быть позже его начала."
                )

            if (
                self.break_start <= self.start_time
                or self.break_end >= self.end_time
            ):
                raise ValidationError(
                    "Перерыв должен быть внутри рабочего времени."
                )


class Absence(models.Model):
    """
    Отсутствие мастера: отпуск, больничный или отгул на диапазон дат.

    Отсутствие сильнее рабочих дней, но не стирает их: если отпуск
    отменить, рабочие дни снова действуют.
    """

    class Kind(models.TextChoices):
        VACATION = "VACATION", "Отпуск"
        SICK = "SICK", "Больничный"
        DAY_OFF = "DAY_OFF", "Отгул"

    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="absences",
        verbose_name="Мастер",
    )
    kind = models.CharField(
        "Тип",
        max_length=20,
        choices=Kind.choices,
        default=Kind.VACATION,
    )
    start_date = models.DateField("С даты")
    end_date = models.DateField("По дату (включительно)")
    comment = models.CharField("Комментарий", max_length=200, blank=True)

    if TYPE_CHECKING:
        master_id: int | None

        # Django создаёт этот метод динамически из-за choices у поля kind;
        # подсказка нужна только редактору (Pylance), при запуске
        # этот блок не выполняется.
        def get_kind_display(self) -> str: ...

    class Meta:
        ordering = ["start_date"]
        verbose_name = "Отсутствие"
        verbose_name_plural = "Отсутствия"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="absence_end_not_before_start",
            ),
        ]

    def __str__(self):
        return (
            f"{self.master} — {self.get_kind_display()} "
            f"{self.start_date}–{self.end_date}"
        )

    def clean(self):
        if self.start_date is None or self.end_date is None:
            return

        if self.end_date < self.start_date:
            raise ValidationError(
                "Дата окончания не может быть раньше даты начала."
            )

        # Мастер ещё не сохранён (его создают в админке вместе с
        # отсутствием): других отсутствий у него в базе пока нет, а фильтр
        # по несохранённому объекту — ошибка.
        if self.master_id is None:
            return

        overlapping = Absence.objects.filter(
            master=self.master,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exclude(pk=self.pk).first()

        if overlapping is not None:
            raise ValidationError(
                "Эти даты пересекаются с другим отсутствием мастера: "
                f"{overlapping.start_date}–{overlapping.end_date}."
            )
