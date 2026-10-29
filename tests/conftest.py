import pytest

from k4lib import i18n


@pytest.fixture(autouse=True)
def spanish():
    """Los tests comprueban mensajes en español (el idioma del código)."""
    i18n.set_language("es")
    yield
    i18n.set_language("es")
