import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    """
    Перед каждым тестом очищаем кэш, чтобы счётчики throttling
    из одного теста не влияли на другие.
    """
    cache.clear()
