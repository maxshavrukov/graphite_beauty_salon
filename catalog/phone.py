"""
Телефоны клиентов: один формат хранения для сайта и админки.

Салон работает только с украинскими номерами, поэтому в базе номер всегда
выглядит как +380XXXXXXXXX (12 цифр с плюсом). Админ по этому номеру звонит
и ищет клиента, так что «0501234567» и «+380501234567» не должны оказаться
двумя разными строками.
"""

import re

PHONE_HINT = "Введите номер в формате 0991234567."


class InvalidPhoneError(ValueError):
    """Строка не похожа на украинский номер телефона."""


def normalize_ua_phone(value: str) -> str:
    """
    Приводит украинский номер к виду +380XXXXXXXXX.

    Принимает то, что реально вводят: «0990172668», «+380990172668»,
    «380990172668», «+38 (099) 017-26-68» (пробелы, скобки и дефисы
    отбрасываются). Остальное — InvalidPhoneError.
    """
    digits = re.sub(r"\D", "", value or "")

    if len(digits) == 10 and digits.startswith("0"):
        national = digits
    elif len(digits) == 12 and digits.startswith("380"):
        national = digits[2:]
    else:
        raise InvalidPhoneError(PHONE_HINT)

    return f"+38{national}"
