"""Test per ``MeasureTool`` (Step 9h)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QKeyEvent, QPainter

from lasercontrolsuite.cad.tools import MeasureTool
from lasercontrolsuite.cad.view import CadGraphicsView


class FakeMouseEvent:
    """Stub minimale di QMouseEvent per chiamare i tool direttamente."""

    def __init__(
        self,
        button: Qt.MouseButton = Qt.MouseButton.LeftButton,
        modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    ) -> None:
        self._button = button
        self._modifiers = modifiers

    def button(self) -> Qt.MouseButton:
        return self._button

    def modifiers(self) -> Qt.KeyboardModifier:
        return self._modifiers


def _key(key: Qt.Key) -> QKeyEvent:
    return QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)


@pytest.fixture
def view(qtbot):
    v = CadGraphicsView()
    qtbot.addWidget(v)
    return v


@pytest.fixture
def tool(view, qtbot):
    t = MeasureTool(view)
    qtbot.addWidget(t._result_dialog)
    view.set_tool(t)
    return t


def test_activate_emits_prompt(view, tool):
    messages: list[str] = []
    view.measureChanged.connect(messages.append)
    tool.activate()
    assert messages
    assert "click" in messages[-1].lower()


def test_distance_two_clicks(view, tool):
    messages: list[str] = []
    view.measureChanged.connect(messages.append)
    ev = FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(3.0, 4.0))
    assert messages
    last = messages[-1]
    assert "5" in last
    assert "mm" in last


def test_angle_mode_three_clicks(view, tool):
    # Toggle modalità via tasto A
    tool.key_press(_key(Qt.Key.Key_A))
    messages: list[str] = []
    view.measureChanged.connect(messages.append)
    ev = FakeMouseEvent()
    # A=(0,0), B=(10,0), C=(10,10) → 90° al vertice B
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 10.0))
    assert messages
    last = messages[-1]
    assert "90.00" in last


def test_escape_resets(view, tool):
    messages: list[str] = []
    view.measureChanged.connect(messages.append)
    ev = FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.key_press(_key(Qt.Key.Key_Escape))
    # Dopo Esc, il primo click conta come "punto 1"
    tool.mouse_press(ev, QPointF(5.0, 5.0))
    assert any("punto 1" in m for m in messages if m)


def test_paint_overlay_does_not_crash(view, tool):
    from PySide6.QtGui import QPixmap

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        tool.paint_overlay(painter)  # nessun punto → no-op
        ev = FakeMouseEvent()
        tool.mouse_press(ev, QPointF(0.0, 0.0))
        tool.paint_overlay(painter)
    finally:
        painter.end()


def test_deactivate_clears_status(view, tool):
    messages: list[str] = []
    view.measureChanged.connect(messages.append)
    tool.deactivate()
    assert messages[-1] == ""


# ---------------------------------------------------------------- nuovi
def test_third_click_after_result_starts_new_measure(view, tool):
    """Dopo che la misura è completa, il click successivo ricomincia."""
    messages: list[str] = []
    view.measureChanged.connect(messages.append)
    ev = FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(3.0, 4.0))
    assert "Distanza" in messages[-1]
    # Terzo click: deve ricominciare da punto 1/2, non aggiungere un terzo punto.
    tool.mouse_press(ev, QPointF(10.0, 10.0))
    assert "punto 1" in messages[-1].lower()


def test_result_dialog_shows_after_measure(view, tool):
    """Il dialog mostra il risultato dopo il secondo click."""
    ev = FakeMouseEvent()
    assert not tool._result_dialog.isVisible()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(3.0, 4.0))
    assert tool._result_dialog.isVisible()
    assert "5" in tool._result_dialog._label.text()


def test_result_dialog_hides_on_new_measure(view, tool):
    """Un nuovo click dopo il risultato nasconde il dialog."""
    ev = FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(3.0, 4.0))
    assert tool._result_dialog.isVisible()
    tool.mouse_press(ev, QPointF(10.0, 10.0))  # ricomincia
    assert not tool._result_dialog.isVisible()


def test_result_dialog_hides_on_escape(view, tool):
    """Esc nasconde il dialog del risultato."""
    ev = FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(3.0, 4.0))
    assert tool._result_dialog.isVisible()
    tool.key_press(_key(Qt.Key.Key_Escape))
    assert not tool._result_dialog.isVisible()


def test_result_dialog_hides_on_deactivate(view, tool):
    """Cambiando tool, il dialog del risultato viene nascosto."""
    ev = FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(3.0, 4.0))
    assert tool._result_dialog.isVisible()
    tool.deactivate()
    assert not tool._result_dialog.isVisible()


def test_angle_result_dialog_contains_degrees(view, tool):
    """Anche in modalità angolo il dialog mostra il risultato."""
    tool.key_press(_key(Qt.Key.Key_A))
    ev = FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 10.0))
    assert tool._result_dialog.isVisible()
    assert "90.00" in tool._result_dialog._label.text()