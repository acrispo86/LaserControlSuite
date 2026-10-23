"""Test per ``MachineSettingsDialog``."""
import pytest

from lasercontrolsuite.config import Machine, MachineOrigin
from lasercontrolsuite.ui.dialogs.machine_settings_dialog import MachineSettingsDialog


def _make(qapp, m=None):
    if m is None:
        m = Machine("Test", 300.0, 200.0, MachineOrigin.BOTTOM_LEFT)
    return MachineSettingsDialog(m)


def test_roundtrip_preserves_values(qapp):
    m = Machine("MyLaser", 410.0, 400.0, MachineOrigin.CENTER)
    dlg = _make(qapp, m)
    out = dlg.machine()
    assert out == m


def test_change_dimensions(qapp):
    dlg = _make(qapp)
    dlg._width_spin.setValue(600.0)
    dlg._height_spin.setValue(500.0)
    out = dlg.machine()
    assert out.width_mm == 600.0
    assert out.height_mm == 500.0


def test_change_origin(qapp):
    dlg = _make(qapp)
    idx = dlg._origin_combo.findData(MachineOrigin.BOTTOM_RIGHT.value)
    assert idx >= 0
    dlg._origin_combo.setCurrentIndex(idx)
    assert dlg.machine().origin is MachineOrigin.BOTTOM_RIGHT


def test_empty_name_falls_back(qapp):
    m = Machine("X", 100.0, 100.0, MachineOrigin.BOTTOM_LEFT)
    dlg = _make(qapp, m)
    dlg._name_edit.setText("   ")
    assert dlg.machine().name == "Laser"