"""Test del sistema di icone inline."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    from lasercontrolsuite.app import get_or_create_qapplication

    return get_or_create_qapplication([])


def test_all_expected_icons_exist() -> None:
    from lasercontrolsuite.resources.icons import available_icons

    expected = {
        "select", "nodes", "pen", "line", "polyline", "bezier",
        "rect", "ellipse", "polygon", "star", "text",
        "undo", "redo",
        "zoom_in", "zoom_out", "fit",
    }
    assert expected <= set(available_icons())


def test_make_icon_returns_non_null(qapp: QApplication) -> None:
    from lasercontrolsuite.resources.icons import make_icon

    icon = make_icon("line")
    assert not icon.isNull()
    assert not icon.pixmap(24, 24).isNull()


def test_make_icon_unknown_raises() -> None:
    from lasercontrolsuite.resources.icons import make_icon

    with pytest.raises(KeyError):
        make_icon("does_not_exist")


def test_icon_color_override(qapp: QApplication) -> None:
    from lasercontrolsuite.resources.icons import make_icon

    icon_white = make_icon("line")
    icon_accent = make_icon("line", color="#00FF00")
    assert not icon_white.pixmap(22, 22).isNull()
    assert not icon_accent.pixmap(22, 22).isNull()


# =====================================================================
# Coerenza toolbar ↔ icone (regressione per il bug "Icona sconosciuta")
# =====================================================================
def test_toolbar_uses_only_available_icons(qapp: QApplication) -> None:
    """Ogni tool della toolbar deve avere un'icona registrata.

    Regressione: la toolbar usava la chiave ``"nodes"``, ma il dizionario
    icone registrava ``"node"``. Aggiungendo un nuovo tool senza la sua
    icona, questo test fallisce con un messaggio chiaro.
    """
    from lasercontrolsuite.resources.icons import available_icons

    # Chiavi usate dai tool nella DrawingToolBar
    toolbar_keys = [
        "select", "nodes", "pen", "line", "polyline", "bezier",
        "rect", "ellipse", "polygon", "star", "text",
    ]
    icons = set(available_icons())
    missing = [k for k in toolbar_keys if k not in icons]
    assert not missing, (
        f"Tool senza icona: {missing}. "
        f"Disponibili: {sorted(icons)}"
    )


def test_toolbar_instantiates_without_keyerror(qapp: QApplication) -> None:
    """La DrawingToolBar si crea senza sollevare (verifica fine-a-fine)."""
    from lasercontrolsuite.cad.toolbar import DrawingToolBar

    tb = DrawingToolBar()
    try:
        # Deve avere un'azione per ogni tool atteso
        action_names = {a.data() for a in tb.actions() if a.data()}
        expected = {
            "select", "nodes", "pen", "line", "polyline", "bezier",
            "rect", "ellipse", "polygon", "star", "text",
        }
        assert expected <= action_names
    finally:
        tb.close()