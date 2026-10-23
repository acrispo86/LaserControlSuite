"""Test del wrapper ConsoleSettings (Step 9b)."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from lasercontrolsuite.config.console_settings import (
    DEFAULT_MACROS,
    ConsoleSettings,
)


@pytest.fixture
def settings(tmp_path):
    ini = tmp_path / "console.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    s = ConsoleSettings(qs)
    yield s
    qs.clear()
    qs.sync()


def test_show_defaults_true(settings):
    for cat in ("ok", "error", "alarm", "status", "msg", "tx"):
        assert settings.get_show_category(cat) is True


def test_show_persist(settings):
    settings.set_show_category("ok", False)
    assert settings.get_show_category("ok") is False
    assert settings.get_show_category("tx") is True


def test_timestamp_default_false(settings):
    assert settings.get_timestamp() is False
    settings.set_timestamp(True)
    assert settings.get_timestamp() is True


def test_autoscroll_default_true(settings):
    assert settings.get_autoscroll() is True
    settings.set_autoscroll(False)
    assert settings.get_autoscroll() is False


def test_macros_seeded_with_defaults(settings):
    macros = settings.get_macros()
    assert list(DEFAULT_MACROS) == macros


def test_macros_add_remove(settings):
    settings.add_macro("G28")
    assert "G28" in settings.get_macros()
    # Deduplica
    settings.add_macro("G28")
    assert settings.get_macros().count("G28") == 1
    settings.remove_macro("G28")
    assert "G28" not in settings.get_macros()


def test_clear(settings):
    settings.set_timestamp(True)
    settings.set_show_category("ok", False)
    settings.clear()
    assert settings.get_timestamp() is False
    assert settings.get_show_category("ok") is True