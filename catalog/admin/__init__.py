"""
Админка каталога, разбитая по смыслу на файлы:

- widgets.py         — общие элементы форм (выбор времени из списка)
- master_forms.py    — форма мастера с таблицей «Обычная неделя»
- masters.py         — карточка мастера на вкладках, прайс мастера
- schedule.py        — общие списки: рабочее время, особые дни, занятое время
- workdays.py        — рабочие дни и отсутствия мастеров (новое расписание)
- service_catalog.py — категории и услуги
- booking_forms.py   — формы новой и существующей записи
- bookings.py        — список записей, фильтры, действия

Django при запуске импортирует этот пакет, поэтому здесь подключаются
все модули с @admin.register. Нужные тестам формы реэкспортируются,
чтобы `from catalog.admin import ...` работал как раньше.
"""

from . import bookings, masters, schedule, service_catalog, workdays
from .booking_forms import BookingChangeForm, BookingCreateForm
from .master_forms import MasterAdminForm, day_field_name

__all__ = [
    "BookingChangeForm",
    "BookingCreateForm",
    "MasterAdminForm",
    "bookings",
    "day_field_name",
    "masters",
    "schedule",
    "service_catalog",
    "workdays",
]
