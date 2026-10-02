"""Общие элементы форм для админки: выбор времени из выпадающего списка."""

from django import forms
from unfold.widgets import UnfoldAdminSelectWidget


def time_choices(first_hour=7, last_hour=22, step_minutes=30):
    """Варианты времени для выпадающего списка: 07:00, 07:30 ... 22:00."""
    choices = [("", "—")]
    minutes = first_hour * 60

    while minutes <= last_hour * 60:
        hours, mins = divmod(minutes, 60)
        choices.append((f"{hours:02d}:{mins:02d}:00", f"{hours:02d}:{mins:02d}"))
        minutes += step_minutes

    return choices


def time_field(label, required=True, step_minutes=30):
    """Поле времени в виде выпадающего списка."""
    return forms.TimeField(
        label=label,
        required=required,
        widget=UnfoldAdminSelectWidget(
            choices=time_choices(step_minutes=step_minutes),
        ),
    )
