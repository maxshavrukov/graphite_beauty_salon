"""
Страница «Расписание» в админке: месячный календарь мастера.

Админ выбирает мастера, кликает дни в календаре, задаёт время работы
(и при желании перерыв) и нажимает «Применить» — расписание на месяц
готово за три действия. Здесь же можно снять рабочие дни и оформить
отпуск или больничный.

Сама страница ничего не решает: все изменения идут через сервисы
schedule_editor (set_work_days, remove_work_days, create_absence), поэтому
действуют те же блокировки и те же проверки конфликтов с записями
клиентов, что и в остальной админке.
"""

import calendar
from datetime import date, datetime, time
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from ..models import Absence, Master
from ..services import get_slot_step
from ..services.schedule_editor import (
    STATE_ABSENT,
    STATE_WORKING,
    create_absence,
    get_month_calendar,
    get_schedule_status,
    remove_work_days,
    set_work_days,
)
from .widgets import time_choices

MONTH_NAMES = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)
WEEKDAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

# Сколько дней можно изменить за один раз: защита от случайного «выбрать всё».
MAX_DATES_PER_ACTION = 62

DEFAULT_START = "10:00:00"
DEFAULT_END = "19:00:00"


def _plural(number: int, one: str, few: str, many: str) -> str:
    """Склонение: 1 день, 2 дня, 5 дней."""
    last_digit, last_two = number % 10, number % 100

    if last_digit == 1 and last_two != 11:
        return one

    if 2 <= last_digit <= 4 and not 12 <= last_two <= 14:
        return few

    return many


def _days(number: int) -> str:
    return f"{number} {_plural(number, 'день', 'дня', 'дней')}"


def _parse_month(raw: str | None, today: date) -> tuple[int, int]:
    """«2026-10» → (2026, 10). Неверное значение — текущий месяц."""
    try:
        year_text, month_text = (raw or "").split("-")
        year, month = int(year_text), int(month_text)
    except ValueError:
        return today.year, today.month

    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        return today.year, today.month

    return year, month


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _month_value(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _parse_time(raw: str | None, label: str, required: bool) -> time | None:
    value = (raw or "").strip()

    if not value:
        if required:
            raise ValidationError(f"Укажите время: {label}.")
        return None

    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue

    raise ValidationError(f"Неверное время: {label}.")


def _parse_date(raw: str | None, label: str) -> date:
    try:
        return date.fromisoformat((raw or "").strip())
    except ValueError:
        raise ValidationError(f"Укажите дату: {label}.") from None


def _parse_selected_dates(raw: str, today: date) -> list[date]:
    """Выбранные в календаре дни: «2026-10-05,2026-10-06» → список дат."""
    found: set[date] = set()

    for part in raw.split(","):
        part = part.strip()

        if not part:
            continue

        try:
            found.add(date.fromisoformat(part))
        except ValueError:
            raise ValidationError("Среди выбранных дней есть неверная дата.") from None

    if not found:
        raise ValidationError("Сначала выберите дни в календаре.")

    if len(found) > MAX_DATES_PER_ACTION:
        raise ValidationError(
            f"За один раз можно изменить не больше {_days(MAX_DATES_PER_ACTION)}.",
        )

    if any(day < today for day in found):
        raise ValidationError("Прошедшие дни менять нельзя.")

    return sorted(found)


def _error_text(error: ValidationError) -> str:
    return "; ".join(error.messages)


def _schedule_url(master: Master, year: int, month: int) -> str:
    query = urlencode({"master": master.pk, "month": _month_value(year, month)})
    return f"{reverse('admin:catalog_workday_schedule')}?{query}"


def _pick_master(raw: str | None, masters: list[Master]) -> Master | None:
    if not masters:
        return None

    try:
        wanted = int(raw or "")
    except ValueError:
        wanted = None

    for master in masters:
        if master.pk == wanted:
            return master

    # По умолчанию — первый работающий мастер.
    return next((m for m in masters if m.is_active), masters[0])


def _apply(request, master: Master, today: date) -> None:
    """Отмечает выбранные дни рабочими."""
    dates = _parse_selected_dates(request.POST.get("dates", ""), today)
    start = _parse_time(request.POST.get("start_time"), "начало работы", True)
    end = _parse_time(request.POST.get("end_time"), "конец работы", True)
    break_start = _parse_time(request.POST.get("break_start"), "начало перерыва", False)
    break_end = _parse_time(request.POST.get("break_end"), "конец перерыва", False)

    if (break_start is None) != (break_end is None):
        raise ValidationError("Для перерыва укажите и начало, и конец.")

    result = set_work_days(master, dates, start, end, break_start, break_end)

    messages.success(
        request,
        f"{master.name}: расписание сохранено на {_days(len(dates))} "
        f"(создано {result.created}, изменено {result.updated}, "
        f"без изменений {result.unchanged}).",
    )


def _clear(request, master: Master, today: date) -> None:
    dates = _parse_selected_dates(request.POST.get("dates", ""), today)
    removed = remove_work_days(master, dates)

    if removed:
        messages.success(
            request,
            f"{master.name}: снято рабочих дней — {removed}.",
        )
    else:
        messages.info(request, "В выбранные дни рабочих дней и не было.")


def _absence(request, master: Master) -> tuple[int, int]:
    kind = request.POST.get("kind", "")

    if kind not in Absence.Kind.values:
        raise ValidationError("Выберите тип отсутствия.")

    start = _parse_date(request.POST.get("start_date"), "первый день")
    end = _parse_date(request.POST.get("end_date"), "последний день")

    if end < start:
        raise ValidationError("Последний день раньше первого.")

    absence = create_absence(
        master,
        kind,
        start,
        end,
        comment=request.POST.get("comment", "").strip()[:200],
    )
    messages.success(
        request,
        f"{master.name}: оформлено — {absence.get_kind_display().lower()} "
        f"с {start:%d.%m.%Y} по {end:%d.%m.%Y}.",
    )
    return start.year, start.month


def schedule_view(model_admin, request):
    """Страница-календарь расписания. Подключается через MasterAdmin.get_urls."""
    if not request.user.has_perm("catalog.change_workday"):
        raise PermissionDenied

    today = timezone.localdate()
    masters = list(Master.objects.order_by("sort_order", "name"))
    master = _pick_master(
        request.POST.get("master") or request.GET.get("master"),
        masters,
    )
    year, month = _parse_month(
        request.POST.get("month") or request.GET.get("month"),
        today,
    )

    form = {
        "start_time": DEFAULT_START,
        "end_time": DEFAULT_END,
        "break_start": "",
        "break_end": "",
    }
    selected: list[str] = []

    if request.method == "POST" and master is not None:
        action = request.POST.get("action")
        selected = [part for part in request.POST.get("dates", "").split(",") if part]
        form = {
            "start_time": request.POST.get("start_time", DEFAULT_START),
            "end_time": request.POST.get("end_time", DEFAULT_END),
            "break_start": request.POST.get("break_start", ""),
            "break_end": request.POST.get("break_end", ""),
        }

        try:
            if action == "apply":
                _apply(request, master, today)
            elif action == "clear":
                _clear(request, master, today)
            elif action == "absence":
                if not request.user.has_perm("catalog.add_absence"):
                    raise PermissionDenied
                year, month = _absence(request, master)
            else:
                raise ValidationError("Неизвестное действие.")
        except ValidationError as error:
            # Ничего не сохранилось. Показываем страницу снова с теми же
            # выбранными днями и временем, чтобы не вводить всё заново.
            messages.error(request, _error_text(error))
        else:
            return redirect(_schedule_url(master, year, month))

    context = {
        **model_admin.admin_site.each_context(request),
        "title": "Расписание",
        "masters": masters,
        "master": master,
        "month_value": _month_value(year, month),
        "month_title": f"{MONTH_NAMES[month - 1]} {year}",
        "weekday_names": WEEKDAY_NAMES,
        "form": form,
        "selected_csv": ",".join(selected),
        "kinds": Absence.Kind.choices,
    }

    break_options = time_choices(step_minutes=get_slot_step())
    context["break_options"] = break_options
    context["time_options"] = break_options[1:]

    if master is not None:
        prev_year, prev_month = _shift_month(year, month, -1)
        next_year, next_month = _shift_month(year, month, 1)
        context["prev_url"] = _schedule_url(master, prev_year, prev_month)
        context["next_url"] = _schedule_url(master, next_year, next_month)
        context["today_url"] = _schedule_url(master, today.year, today.month)
        context["status"] = get_schedule_status(master, today)
        context["weeks"] = _build_weeks(master, year, month, today)

        # Если в месяце уже есть рабочие дни, предлагаем их время как
        # стартовое: обычно график у мастера повторяется.
        if request.method != "POST":
            first_work_day = next(
                (
                    cell["work_day"]
                    for week in context["weeks"]
                    for cell in week
                    if cell and cell["work_day"]
                ),
                None,
            )
            if first_work_day is not None:
                form["start_time"] = first_work_day.start_time.strftime("%H:%M:00")
                form["end_time"] = first_work_day.end_time.strftime("%H:%M:00")

    return TemplateResponse(request, "catalog/admin/schedule.html", context)


def _build_weeks(master: Master, year: int, month: int, today: date):
    """Сетка месяца: недели по 7 ячеек, пустые клетки вне месяца — None."""
    by_date = {
        item.day: item for item in get_month_calendar(master, year, month, today)
    }
    weeks = []

    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        cells = []

        for day in week:
            if day.month != month:
                cells.append(None)
                continue

            item = by_date[day]
            work_day = item.work_day
            hours = ""
            has_break = False

            if work_day is not None:
                hours = f"{work_day.start_time:%H:%M}–{work_day.end_time:%H:%M}"
                has_break = work_day.break_start is not None

            cells.append(
                {
                    "iso": day.isoformat(),
                    "number": day.day,
                    "weekday": day.weekday(),
                    "state": item.state,
                    "is_working": item.state == STATE_WORKING,
                    "is_absent": item.state == STATE_ABSENT,
                    "is_today": item.is_today,
                    "is_past": item.is_past,
                    "is_weekend": day.weekday() >= 5,
                    "work_day": work_day,
                    "hours": hours,
                    "has_break": has_break,
                    "bookings": item.bookings_count,
                    "absence": (
                        item.absence.get_kind_display() if item.absence else ""
                    ),
                }
            )

        weeks.append(cells)

    return weeks
