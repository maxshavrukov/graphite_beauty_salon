"""
Методы get_<поле>_display() у моделей с choices должны возвращать подписи.

Django создаёт их сам, но не трогает, если в классе уже есть метод с тем же
именем. Заглушка «def get_status_display(self) -> str: ...», оставленная вне
блока TYPE_CHECKING, молча заменяет настоящий метод пустым: админка начинает
показывать пустой статус, а ошибок и падений при этом нет.
"""

from django.apps import apps
from django.test import SimpleTestCase

from catalog.models import Booking


class ChoiceLabelsTests(SimpleTestCase):
    def test_every_choice_field_has_a_working_display_method(self):
        checked = 0

        for model in apps.get_app_config("catalog").get_models():
            for field in model._meta.fields:
                choices = getattr(field, "flatchoices", None)

                if not choices:
                    continue

                value, label = choices[0]
                instance = model()
                setattr(instance, field.attname, value)

                with self.subTest(model=model.__name__, field=field.name):
                    display = getattr(instance, f"get_{field.name}_display")()

                    self.assertEqual(display, str(label))

                checked += 1

        self.assertGreater(checked, 0)

    def test_booking_status_label_is_human_readable(self):
        booking = Booking(status=Booking.Status.NEW)

        self.assertEqual(booking.get_status_display(), "Новая")
