"""Test della tool options bar."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    from lasercontrolsuite.app import get_or_create_qapplication

    return get_or_create_qapplication([])


@pytest.fixture()
def bar(qapp: QApplication):
    from lasercontrolsuite.ui.widgets.tool_options_bar import ToolOptionsBar

    b = ToolOptionsBar()
    yield b
    b.close()


# =====================================================================
# Valori di default
# =====================================================================
def test_defaults(bar) -> None:
    assert bar.polygon_sides == 6
    assert bar.star_points == 5
    assert bar.star_inner_ratio == 0.4
    assert bar.text_size_mm == 10.0


# =====================================================================
# Visibilità per tool
# =====================================================================
def test_visibility_for_polygon(bar) -> None:
    bar.show_for_tool("polygon")
    assert bar.is_option_visible("polygon_sides")
    assert not bar.is_option_visible("star_points")
    assert not bar.is_option_visible("star_inner_ratio")
    assert not bar.is_option_visible("text_size")


def test_visibility_for_star(bar) -> None:
    bar.show_for_tool("star")
    assert bar.is_option_visible("star_points")
    assert bar.is_option_visible("star_inner_ratio")
    assert not bar.is_option_visible("polygon_sides")
    assert not bar.is_option_visible("text_size")


def test_visibility_for_text(bar) -> None:
    bar.show_for_tool("text")
    assert bar.is_option_visible("text_size")
    assert not bar.is_option_visible("polygon_sides")
    assert not bar.is_option_visible("star_points")


def test_visibility_for_select_hides_all(bar) -> None:
    bar.show_for_tool("select")
    assert not bar.is_option_visible("polygon_sides")
    assert not bar.is_option_visible("star_points")
    assert not bar.is_option_visible("star_inner_ratio")
    assert not bar.is_option_visible("text_size")


def test_switching_between_tools_updates_visibility(bar) -> None:
    bar.show_for_tool("polygon")
    assert bar.is_option_visible("polygon_sides")
    bar.show_for_tool("star")
    assert not bar.is_option_visible("polygon_sides")
    assert bar.is_option_visible("star_points")
    bar.show_for_tool("select")
    assert not bar.is_option_visible("star_points")


# =====================================================================
# is_option_visible — contratto
# =====================================================================
def test_is_option_visible_unknown_name_raises(bar) -> None:
    with pytest.raises(KeyError):
        bar.is_option_visible("does_not_exist")


def test_is_option_visible_works_without_show(bar) -> None:
    """Deve funzionare anche senza ``show()`` del widget top-level.

    Regressione: il test originale usava ``isVisible()``, che ritorna sempre
    False se il widget non è mostrato. ``is_option_visible()`` si basa su
    ``isHidden()`` ed è indipendente dalla gerarchia di visibilità.
    """
    # Il fixture non chiama show(); verifichiamo comunque il comportamento.
    bar.show_for_tool("polygon")
    assert bar.is_option_visible("polygon_sides")