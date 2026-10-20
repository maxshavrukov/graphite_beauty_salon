from django.db import migrations, models
from django.db.models import Q, F


def validate_legacy_rows(apps, schema_editor):
    """Fail with actionable IDs rather than silently rewriting legacy data."""
    MasterService = apps.get_model("catalog", "MasterService")
    Booking = apps.get_model("catalog", "Booking")
    TimeBlock = apps.get_model("catalog", "TimeBlock")

    invalid_master_services = list(
        MasterService.objects.filter(Q(price__lt=0) | Q(duration__lte=0))
        .values_list("pk", "price", "duration")[:10]
    )
    invalid_bookings = list(
        Booking.objects.filter(Q(price__lt=0) | Q(duration__lte=0))
        .values_list("pk", "price", "duration")[:10]
    )
    invalid_time_blocks = list(
        TimeBlock.objects.filter(Q(start_time__gte=F("end_time")))
        .values_list("pk", "start_time", "end_time")[:10]
    )

    errors = []
    if invalid_master_services:
        errors.append(
            "MasterService (pk, price, duration): "
            f"{invalid_master_services}"
        )
    if invalid_bookings:
        errors.append(f"Booking (pk, price, duration): {invalid_bookings}")
    if invalid_time_blocks:
        errors.append(
            "TimeBlock (pk, start_time, end_time): "
            f"{invalid_time_blocks}"
        )

    if errors:
        raise RuntimeError(
            "Нельзя применить миграцию 0013: найдены некорректные старые данные. "
            "Исправьте указанные записи вручную и повторите migrate.\n"
            + "\n".join(errors)
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0012_booking_event"),
    ]

    operations = [
        migrations.RunPython(validate_legacy_rows, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="bookingevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("CREATED", "Создана"),
                    ("STATUS", "Смена статуса"),
                    ("RESCHEDULED", "Перенос / изменение записи"),
                    ("CLIENT_UPDATED", "Изменение данных клиента"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="masterservice",
            constraint=models.CheckConstraint(
                condition=Q(price__gte=0),
                name="master_service_price_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="masterservice",
            constraint=models.CheckConstraint(
                condition=Q(duration__gt=0),
                name="master_service_duration_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="timeblock",
            constraint=models.CheckConstraint(
                condition=Q(start_time__lt=F("end_time")),
                name="time_block_start_before_end",
            ),
        ),
        migrations.AddIndex(
            model_name="timeblock",
            index=models.Index(
                fields=["master", "date", "start_time"],
                name="timeblock_master_date_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="booking",
            constraint=models.CheckConstraint(
                condition=Q(price__gte=0),
                name="booking_price_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="booking",
            constraint=models.CheckConstraint(
                condition=Q(duration__gt=0),
                name="booking_duration_positive",
            ),
        ),
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(
                fields=["master", "date", "status"],
                name="booking_master_date_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(
                fields=["master", "date", "start_time"],
                name="booking_master_date_time_idx",
            ),
        ),
    ]
