"""
Форма мастера с таблицей «Обычная неделя».

Каждый день недели — одно составное поле (DayScheduleField): галочка
«Работает», время начала и конца и необязательный перерыв. Перевод
между этим видом и записями WorkingHours делает
services/weekly_schedule.py.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import format_html, format_html_join
from unfold.widgets import UnfoldAdminSelectWidget

from ..models import Master, WorkingHours
from ..services.weekly_schedule import (
    DaySchedule,
    get_day_error,
    get_weekly_schedule,
    save_weekly_schedule,
)
from .widgets import time_choices


# [(0, "Понедельник"), (1, "Вторник"), ...]
WEEKDAYS: list[tuple[int, str]] = [
    (int(value), str(label)) for value, label in WorkingHours.Weekday.choices
]


def day_field_name(weekday: int) -> str:
    """Имя поля формы для одного дня недели: day0 (пн) ... day6 (вс)."""
    return f"day{weekday}"


class DayScheduleWidget(forms.MultiWidget):
    """
    Одна строка дня недели: галочка «Работает», время начала и конца
    и необязательный перерыв. Все пять элементов выводятся в один ряд.
    """

    CAPTIONS = ("Работает", "С", "До", "Перерыв с", "Перерыв до")

    def __init__(self, attrs=None):
        widgets = [forms.CheckboxInput()] + [
            UnfoldAdminSelectWidget(choices=time_choices()) for _ in range(4)
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        """DaySchedule -> список значений для пяти элементов."""
        if isinstance(value, DaySchedule):
            return [
                value.works,
                value.start,
                value.end,
                value.break_start,
                value.break_end,
            ]

        return [False, None, None, None, None]

    def render(self, name, value, attrs=None, renderer=None):
        values = value if isinstance(value, list) else self.decompress(value)
        base_id = (attrs or {}).get("id")
        cells = []

        for index, (caption, widget) in enumerate(zip(self.CAPTIONS, self.widgets)):
            widget_attrs = {"id": f"{base_id}_{index}"} if base_id else {}
            control = widget.render(
                f"{name}_{index}",
                values[index],
                widget_attrs,
                renderer,
            )
            cells.append(
                format_html(
                    '<div style="display:flex;flex-direction:column;'
                    'gap:4px;min-width:96px;">'
                    '<span style="font-size:12px;opacity:.7;">{}</span>{}</div>',
                    caption,
                    control,
                )
            )

        return format_html(
            '<div style="display:flex;flex-wrap:wrap;'
            'align-items:flex-end;gap:16px;">{}</div>',
            format_html_join("", "{}", ((cell,) for cell in cells)),
        )


class DayScheduleField(forms.MultiValueField):
    """Поле одного дня недели. Значение — DaySchedule."""

    widget = DayScheduleWidget

    def __init__(self, **kwargs):
        fields = (
            forms.BooleanField(required=False),
            forms.TimeField(required=False),
            forms.TimeField(required=False),
            forms.TimeField(required=False),
            forms.TimeField(required=False),
        )
        super().__init__(
            fields=fields,
            require_all_fields=False,
            required=False,
            **kwargs,
        )

    def compress(self, data_list):
        if not data_list:
            return DaySchedule(works=False)

        works, start, end, break_start, break_end = data_list

        return DaySchedule(
            works=bool(works),
            start=start,
            end=end,
            break_start=break_start,
            break_end=break_end,
        )

    def validate(self, value):
        super().validate(value)

        error = get_day_error(value)
        if error is not None:
            raise ValidationError(error)


def week_form_fields() -> dict[str, forms.Field]:
    """Семь полей (по одному на день). Django требует объявить их заранее."""
    return {
        day_field_name(weekday): DayScheduleField(label=label)
        for weekday, label in WEEKDAYS
    }


# Имена семи полей по порядку: day0, day1, ... day6.
WEEK_FIELDS: tuple[str, ...] = tuple(
    day_field_name(weekday) for weekday, _ in WEEKDAYS
)


class MasterBaseForm(forms.ModelForm):
    """Форма мастера: обычные поля мастера плюс недельный график."""

    class Meta:
        model = Master
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Заполняем таблицу недели тем, что уже сохранено в базе.
        week = get_weekly_schedule(self.instance)

        for weekday, _label in WEEKDAYS:
            self.initial[day_field_name(weekday)] = week[weekday]

    def save_week(self):
        """
        Сохраняет в базу только те дни, которые админ изменил в форме.
        Нетронутые дни не перезаписываются.
        """
        changed = set(self.changed_data)
        week = {}

        for weekday, _label in WEEKDAYS:
            name = day_field_name(weekday)
            day = self.cleaned_data.get(name)

            if name in changed and isinstance(day, DaySchedule):
                week[weekday] = day

        if week:
            save_weekly_schedule(self.instance, week)


# Итоговая форма: базовая + 7 полей недели.
MasterAdminForm = type("MasterAdminForm", (MasterBaseForm,), week_form_fields())
