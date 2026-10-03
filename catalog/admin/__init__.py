"""
Админка каталога, разбитая по смыслу на файлы:

- widgets.py         — общие элементы форм (выбор времени из списка)
- masters.py         — карточка мастера на вкладках, прайс мастера
- schedule.py        — общий список занятого времени
- workdays.py        — рабочие дни и отсутствия мастеров
- service_catalog.py — категории и услуги
- booking_forms.py   — формы новой и существующей записи
- bookings.py        — список записей, фильтры, действия

Django при запуске импортирует этот пакет, поэтому здесь подключаются
все модули с @admin.register. Нужные тестам формы реэкспортируются,
чтобы `from catalog.admin import ...` работал.
"""

from . import bookings, masters, schedule, service_catalog, workdays
from .booking_forms import BookingChangeForm, BookingCreateForm

__all__ = [
    "BookingChangeForm",
    "BookingCreateForm",
    "bookings",
    "masters",
    "schedule",
    "service_catalog",
    "workdays",
]
