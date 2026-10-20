"""Команда seed_demo: безопасна, повторяема и даёт рабочие данные для сайта."""

from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import Master, MasterService, Service, WorkDay
from catalog.services import get_available_dates_for_service


class SeedDemoTests(TestCase):
    @override_settings(DEBUG=False)
    def test_refuses_to_run_without_debug(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", verbosity=0)

        self.assertEqual(Master.objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_creates_data_that_the_site_can_use(self):
        call_command("seed_demo", verbosity=0)

        self.assertEqual(Master.objects.count(), 3)
        self.assertEqual(Service.objects.count(), 6)
        self.assertTrue(WorkDay.objects.exists())

        service = Service.objects.get(slug="womens-haircut")
        today = timezone.localdate()
        dates = get_available_dates_for_service(
            service, today, today + timedelta(days=14),
        )

        self.assertTrue(dates)

    @override_settings(DEBUG=True)
    def test_second_run_does_not_duplicate(self):
        call_command("seed_demo", verbosity=0)
        counts = (
            Master.objects.count(),
            Service.objects.count(),
            MasterService.objects.count(),
            WorkDay.objects.count(),
        )

        call_command("seed_demo", verbosity=0)

        self.assertEqual(
            counts,
            (
                Master.objects.count(),
                Service.objects.count(),
                MasterService.objects.count(),
                WorkDay.objects.count(),
            ),
        )
