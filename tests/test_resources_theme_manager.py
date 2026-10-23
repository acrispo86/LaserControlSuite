"""Test del ThemeManager (Step 9d)."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings

from lasercontrolsuite.resources.theme import DARK, LIGHT, Theme
from lasercontrolsuite.resources.theme_manager import ThemeManager


@pytest.fixture
def manager(tmp_path, qapp):
    """ThemeManager isolato su file INI in tmp_path."""
    ini = tmp_path / "theme.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    m = ThemeManager.reset_for_tests(qs)
    yield m
    qs.clear()
    qs.sync()
    # Ripristina il singleton di default (dark, QSettings reale)
    ThemeManager.reset_for_tests()


def test_singleton_returns_same_instance(qapp):
    a = ThemeManager.instance()
    b = ThemeManager.instance()
    assert a is b


def test_default_is_dark(manager):
    assert manager.current_name() == "dark"
    assert manager.theme() is DARK


def test_set_theme_light(manager):
    manager.set_theme("light")
    assert manager.current_name() == "light"
    assert manager.theme() is LIGHT


def test_set_theme_emits_signal(manager, qtbot):
    received: list[str] = []
    manager.themeChanged.connect(lambda n: received.append(n))
    manager.set_theme("light")
    assert received == ["light"]


def test_set_theme_same_name_no_signal(manager):
    received: list[str] = []
    manager.themeChanged.connect(lambda n: received.append(n))
    manager.set_theme("dark")  # già dark
    assert received == []


def test_set_theme_invalid_raises(manager):
    with pytest.raises(ValueError):
        manager.set_theme("neon")


def test_load_preference_default(manager):
    name = manager.load_preference()
    assert name == "dark"


def test_load_preference_roundtrip(manager):
    manager.set_theme("light")
    # Nuovo manager con stesso QSettings → legge "light"
    m2 = ThemeManager.reset_for_tests(manager._qs)
    name = m2.load_preference()
    assert name == "light"
    assert m2.theme() is LIGHT


def test_qss_uses_current_theme(manager):
    manager.set_theme("light")
    qss = manager.qss()
    # Colore di sfondo del tema chiaro
    assert LIGHT.bg_window in qss


def test_dark_light_differ():
    # Chrome: differenze evidenti
    assert DARK.bg_window != LIGHT.bg_window
    assert DARK.fg_primary != LIGHT.fg_primary
    assert DARK.accent != LIGHT.accent
    # Tela: sfondo esterno diverso (più chiaro nel tema light)
    assert DARK.canvas_outside_bg != LIGHT.canvas_outside_bg
    # Area di lavoro: bianca in entrambi (standard industriale)
    assert DARK.canvas_workarea_bg == LIGHT.canvas_workarea_bg
    # Entità: scure in entrambi (per leggibilità su area bianca)
    assert DARK.entity_default == LIGHT.entity_default