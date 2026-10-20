from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
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
        category_id: int

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

    if TYPE_CHECKING:
        master_id: int
        service_id: int

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["master", "service"],
                name="unique_master_service",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="master_service_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(duration__gt=0),
                name="master_service_duration_positive",
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

    if TYPE_CHECKING:
        master_id: int | None

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name = "Блокировка времени"
        verbose_name_plural = "Блокировки времени"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(start_time__lt=models.F("end_time")),
                name="time_block_start_before_end",
            ),
        ]
        indexes = [
            models.Index(
                fields=["master", "date", "start_time"],
                name="timeblock_master_date_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.start_time is None or self.end_time is None:
            return

        if self.start_time >= self.end_time:
            raise ValidationError(
                "Время окончания должно быть позже времени начала."
            )

        if self.master_id is None or self.date is None:
            return

        block_start = datetime.combine(self.date, self.start_time)
        block_end = datetime.combine(self.date, self.end_time)
        conflicts = []
        bookings = Booking.objects.filter(
            master_id=self.master_id,
            date=self.date,
            status__in=Booking.ACTIVE_STATUSES,
        ).only("id", "start_time", "duration", "client_name")
        for booking in bookings:
            booking_start = datetime.combine(self.date, booking.start_time)
            booking_end = booking_start + timedelta(minutes=booking.duration)
            if booking_start < block_end and booking_end > block_start:
                conflicts.append(booking)

        if conflicts:
            labels = ", ".join(
                f"#{item.pk} ({item.start_time:%H:%M}, {item.client_name})"
                for item in conflicts[:5]
            )
            suffix = " …" if len(conflicts) > 5 else ""
            raise ValidationError(
                "Блокировка пересекается с активными записями: "
                f"{labels}{suffix}. Сначала перенесите или отмените эти записи."
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

    # Статусы, при которых запись занимает время мастера. Единственное
    # место, где это решено: расчёт слотов, проверка записи, редактор
    # расписания и админка берут список отсюда. Добавляя новый статус,
    # решите, занимает ли он время, и при необходимости поправьте кортеж.
    ACTIVE_STATUSES = (Status.NEW, Status.CONFIRMED)

    # Какие смены статуса разрешены: ключ — текущий статус, значение —
    # статусы, в которые запись можно перевести. Единственное место, где
    # это решено: форма в админке, массовые действия и сервис
    # change_booking_status берут правила отсюда.
    #
    # NEW -> COMPLETED / NO_SHOW нарочно нет: запись сначала подтверждают,
    # а уже потом отмечают визит. COMPLETED <-> NO_SHOW оставлены для
    # исправления ошибки администратора. Из CANCELLED выхода нет: время
    # уже могли занять, а проверок при смене статуса нет.
    ALLOWED_TRANSITIONS = {
        Status.NEW: (Status.CONFIRMED, Status.CANCELLED),
        Status.CONFIRMED: (
            Status.COMPLETED,
            Status.NO_SHOW,
            Status.CANCELLED,
        ),
        Status.COMPLETED: (Status.NO_SHOW,),
        Status.NO_SHOW: (Status.COMPLETED,),
        Status.CANCELLED: (),
    }

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

    if TYPE_CHECKING:
        events: Any
        master_id: int
        service_id: int

        # Django создаёт этот метод в рантайме из choices у status; подсказка
        # нужна только редактору (Pylance). Она обязана стоять внутри
        # TYPE_CHECKING: иначе настоящий метод заменится пустым и вернёт None.
        def get_status_display(self) -> str: ...

    class Meta:
        ordering = ["date", "start_time"]
        verbose_name = "Запись"
        verbose_name_plural = "Записи"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name="booking_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(duration__gt=0),
                name="booking_duration_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["master", "date", "status"],
                name="booking_master_date_status_idx",
            ),
            models.Index(
                fields=["master", "date", "start_time"],
                name="booking_master_date_time_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.date} {self.start_time:%H:%M} — "
            f"{self.client_name} — {self.master}"
        )


class BookingEvent(models.Model):
    """
    Журнал записи: кто и когда её создал, перенёс или сменил статус.

    Строки только добавляются, а не правятся. По ним админ видит историю
    записи, а позже на них же будут строиться уведомления клиенту.
    """

    class Kind(models.TextChoices):
        CREATED = "CREATED", "Создана"
        STATUS = "STATUS", "Смена статуса"
        RESCHEDULED = "RESCHEDULED", "Перенос / изменение записи"
        CLIENT_UPDATED = "CLIENT_UPDATED", "Изменение данных клиента"

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="events",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # Кто сделал: сотрудник из админки. Пусто — клиент с сайта или система.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    if TYPE_CHECKING:
        booking_id: int
        actor_id: int | None

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Событие записи"
        verbose_name_plural = "События записей"

    def __str__(self):
        return f"{self.booking_id} — {self.kind} — {self.created_at:%Y-%m-%d %H:%M}"


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

        # Если WorkDay переносится на другую дату/мастера, проверяем, не
        # потеряет ли исходная дата поддержку для онлайн-записей, которые
        # действительно помещались в исходный график.
        original = None
        if self.pk is not None:
            original = WorkDay.objects.filter(pk=self.pk).first()

        def fits_intervals(booking, intervals, target_date):
            start = datetime.combine(target_date, booking.start_time)
            end = start + timedelta(minutes=booking.duration)
            return any(
                start >= datetime.combine(target_date, interval_start)
                and end <= datetime.combine(target_date, interval_end)
                for interval_start, interval_end in intervals
            )

        if original is not None and (
            original.master_id != self.master_id or original.date != self.date
        ):
            old_bookings = Booking.objects.filter(
                master_id=original.master_id,
                date=original.date,
                source=Booking.Source.ONLINE,
                status__in=Booking.ACTIVE_STATUSES,
            )
            if any(
                fits_intervals(item, original.get_intervals(), original.date)
                for item in old_bookings
            ):
                raise ValidationError(
                    "Нельзя перенести рабочий день: на исходную дату есть "
                    "онлайн-запись, которая использует этот график. "
                    "Сначала перенесите или отмените запись."
                )

        # При изменении времени блокируем только ухудшение относительно
        # исходного графика. Уже существующая ручная запись вне расписания —
        # допустимое исключение проекта, и она не должна запрещать безвредную
        # правку рабочего дня.
        if (
            original is not None
            and original.master_id == self.master_id
            and original.date == self.date
            and self.master_id is not None
            and self.date is not None
        ):
            proposed_intervals = self.get_intervals()
            old_intervals = original.get_intervals()
            bookings = Booking.objects.filter(
                master_id=self.master_id,
                date=self.date,
                source=Booking.Source.ONLINE,
                status__in=Booking.ACTIVE_STATUSES,
            )
            conflicts = [
                item for item in bookings
                if fits_intervals(item, old_intervals, self.date)
                and not fits_intervals(item, proposed_intervals, self.date)
            ]
            if conflicts:
                labels = ", ".join(
                    f"#{item.pk} ({item.start_time:%H:%M}, {item.client_name})"
                    for item in conflicts[:5]
                )
                suffix = " …" if len(conflicts) > 5 else ""
                raise ValidationError(
                    "Изменение рабочего времени конфликтует с онлайн-записями: "
                    f"{labels}{suffix}. Сначала перенесите или отмените эти записи."
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

        booking_conflicts = Booking.objects.filter(
            master_id=self.master_id,
            date__range=(self.start_date, self.end_date),
            status__in=Booking.ACTIVE_STATUSES,
        ).order_by("date", "start_time")
        if booking_conflicts.exists():
            examples = list(
                booking_conflicts.values_list(
                    "date", "start_time", "client_name", "id",
                )[:5]
            )
            labels = ", ".join(
                f"#{booking_id} ({booking_date:%d.%m.%Y} {booking_time:%H:%M}, {name})"
                for booking_date, booking_time, name, booking_id in examples
            )
            suffix = " …" if booking_conflicts.count() > 5 else ""
            raise ValidationError(
                "Нельзя оформить отсутствие: в этот период есть активные "
                f"записи: {labels}{suffix}. Сначала перенесите или отмените их."
            )

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
