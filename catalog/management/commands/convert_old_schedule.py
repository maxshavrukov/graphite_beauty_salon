from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.services.schedule_conversion import convert_old_schedule


class Command(BaseCommand):
    help = (
        "Переносит старое расписание (обычная неделя и исключения) "
        "в новые рабочие дни на заданный период вперёд."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=45,
            help="На сколько дней вперёд переносить (по умолчанию 45).",
        )
        parser.add_argument(
            "--from-date",
            type=date.fromisoformat,
            default=None,
            help="С какой даты, ГГГГ-ММ-ДД (по умолчанию сегодня).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, что будет сделано, ничего не сохраняя.",
        )

    def handle(self, *args, **options):
        date_from = options["from_date"] or timezone.localdate()
        date_to = date_from + timedelta(days=options["days"])
        dry_run = options["dry_run"]

        report = convert_old_schedule(date_from, date_to, dry_run=dry_run)

        self.stdout.write(f"Период: {date_from:%d.%m.%Y} — {date_to:%d.%m.%Y}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("ПРОБНЫЙ ЗАПУСК: ничего не сохранено.")
            )

        verb = "Будет создано" if dry_run else "Создано"
        self.stdout.write(self.style.SUCCESS(f"{verb} рабочих дней: {report.created}"))
        self.stdout.write(
            f"Уже были (не тронуты): {report.skipped_existing}"
        )
        self.stdout.write(
            f"Закрытых дней по исключениям (рабочий день не создан): "
            f"{report.closed_days}"
        )

        if report.closed_with_reason:
            self.stdout.write("")
            self.stdout.write(
                "Закрытые дни с причиной — если это были отпуска или "
                "больничные, оформите их в «Отсутствиях»:"
            )
            for line in report.closed_with_reason:
                self.stdout.write(f"  - {line}")

        if report.warnings:
            self.stdout.write("")
            for warning in report.warnings:
                self.stdout.write(self.style.WARNING(f"Внимание: {warning}"))
