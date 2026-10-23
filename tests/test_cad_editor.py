"""Test del CanvasEditor (clipboard, nudge, align, booleane, ...)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from lasercontrolsuite.cad.editor import CanvasEditor
from lasercontrolsuite.cad.view import CadGraphicsView
from lasercontrolsuite.core.entities import PolylineEntity


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    from lasercontrolsuite.app import get_or_create_qapplication
    return get_or_create_qapplication([])


@pytest.fixture
def ctx(qapp):
    v = CadGraphicsView()
    v.resize(800, 600)
    v.show()
    qapp.processEvents()
    yield v, v.editor
    v.close()


def _add_rect(view, x, y, w=10.0, h=5.0):
    doc = view.cad_scene.document
    e = PolylineEntity.rect(doc.active_layer_id, x, y, w, h)
    doc.add_entity(e)
    return e


def _select(view, entities):
    scene = view.cad_scene
    scene.clearSelection()
    for e in entities:
        item = scene.entity_item(e.id)
        if item:
            item.setSelected(True)
    # forza il segnale di selezione
    view.cad_scene.selectionChanged.emit()


def test_copy_paste(ctx):
    view, editor = ctx
    a = _add_rect(view, 0, 0)
    _select(view, [a])
    n = editor.copy_selection()
    assert n == 1
    n = editor.paste(20, 0)
    assert n == 1
    assert len(view.cad_scene.document.entities) == 2


def test_delete_selection(ctx):
    view, editor = ctx
    a = _add_rect(view, 0, 0)
    _select(view, [a])
    n = editor.delete_selection()
    assert n == 1
    assert len(view.cad_scene.document.entities) == 0


def test_boolean_union(ctx):
    view, editor = ctx
    a = _add_rect(view, 0, 0, 10, 10)
    b = _add_rect(view, 5, 0, 10, 10)
    _select(view, [a, b])
    n, warnings = editor.boolean_union()
    assert n == 1
    assert not warnings
    assert len(view.cad_scene.document.entities) == 1


def test_boolean_difference(ctx):
    view, editor = ctx
    a = _add_rect(view, 0, 0, 10, 10)
    b = _add_rect(view, 2, 2, 5, 5)
    _select(view, [a, b])
    n, warnings = editor.boolean_difference()
    assert n == 2
    assert not warnings
    assert len(view.cad_scene.document.entities) == 2


def test_boolean_undo(ctx):
    view, editor = ctx
    a = _add_rect(view, 0, 0, 10, 10)
    b = _add_rect(view, 5, 0, 10, 10)
    _select(view, [a, b])
    editor.boolean_union()
    assert len(view.cad_scene.document.entities) == 1
    view.cad_scene.undo_stack.undo()
    assert len(view.cad_scene.document.entities) == 2


def test_boolean_less_than_two_entities(ctx):
    view, editor = ctx
    a = _add_rect(view, 0, 0)
    _select(view, [a])
    n, warnings = editor.boolean_union()
    assert n == 0
    assert any("almeno due entità" in w for w in warnings)