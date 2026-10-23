"""Test per ``config.settings.Settings``.

Usa un ``QSettings`` INI su file temporaneo: nessuna scrittura nel registro
di sistema.
"""
import pytest
from PySide6.QtCore import QSettings

from lasercontrolsuite.config.machine import (
    DEFAULT_WORK_AREA_MM,
    Machine,
    MachineOrigin,
)
from lasercontrolsuite.config.settings import Settings


@pytest.fixture
def settings(qapp, tmp_path):
    qs = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    qs.clear()
    s = Settings(qsettings=qs)
    yield s
    qs.clear()


def test_default_machine_created_on_first_read(settings):
    m = settings.get_active_machine()
    assert m.name == "Laser"
    assert m.width_mm == DEFAULT_WORK_AREA_MM
    assert m.height_mm == DEFAULT_WORK_AREA_MM
    assert m.origin is MachineOrigin.BOTTOM_LEFT


def test_set_then_get(settings):
    m = Machine("Atomstack A5", 410.0, 400.0, MachineOrigin.BOTTOM_LEFT)
    settings.set_active_machine(m)
    m2 = settings.get_active_machine()
    assert m2 == m


def test_change_origin(settings):
    m = Machine("Laser", 300.0, 200.0, MachineOrigin.CENTER)
    settings.set_active_machine(m)
    m2 = settings.get_active_machine()
    assert m2.origin is MachineOrigin.CENTER


def test_multiple_machines_kept(settings):
    a = Machine("A", 300.0, 300.0, MachineOrigin.BOTTOM_LEFT)
    b = Machine("B", 600.0, 400.0, MachineOrigin.BOTTOM_RIGHT)
    settings.set_active_machine(a)
    settings.set_active_machine(b)
    assert {m.name for m in settings.list_machines()} == {"A", "B"}
    assert settings.get_active_machine().name == "B"


def test_overwrite_same_name(settings):
    m = Machine("X", 100.0, 100.0, MachineOrigin.BOTTOM_LEFT)
    settings.set_active_machine(m)
    m2 = Machine("X", 200.0, 300.0, MachineOrigin.CENTER)
    settings.set_active_machine(m2)
    machines = settings.list_machines()
    assert len(machines) == 1
    assert machines[0].width_mm == 200.0
    assert machines[0].origin is MachineOrigin.CENTER


def test_active_machine_falls_back_to_first_when_name_missing(settings):
    m = Machine("Real", 200.0, 200.0, MachineOrigin.BOTTOM_LEFT)
    settings.set_active_machine(m)
    settings._qs.setValue("active_machine", "NonExisting")
    settings._qs.sync()
    got = settings.get_active_machine()
    assert got.name == "Real"


def test_clear(settings):
    settings.set_active_machine(Machine("X", 10, 10, MachineOrigin.BOTTOM_LEFT))
    settings.clear()
    m = settings.get_active_machine()  # ricrea il default
    assert m.name == "Laser"

def test_qss_covers_qdialog(qapp):
    from lasercontrolsuite.resources.theme import THEME
    qss = THEME.qss()
    assert "QDialog" in qss
    assert "QPushButton" in qss
    assert "QComboBox" in qss
    assert "QGroupBox" in qss