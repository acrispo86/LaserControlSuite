"""Test del metodo ``CanvasEditor.import_entities``."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lasercontrolsuite.core.entities import PolylineEntity  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    from lasercontrolsuite.app import get_or_create_qapplication

    return get_or_create_qapplication([])


@pytest.fixture()
def view(qapp: QApplication):
    from lasercontrolsuite.cad.view import CadGraphicsView

    v = CadGraphicsView()
    v.resize(800, 600)
    v.show()
    qapp.processEvents()
    yield v
    v.close()


def test_import_entities_adds_all_at_once(view) -> None:
    doc = view.cad_scene.document
    entities = [
        PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0),
        PolylineEntity.rect(doc.active_layer_id, 5.0, 5.0, 2.0, 2.0),
    ]
    n = view.editor.import_entities(entities, "Test import")
    assert n == 2
    assert len(doc.entities) == 2


def test_import_entities_undo_removes_all(view) -> None:
    doc = view.cad_scene.document
    entities = [
        PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0),
        PolylineEntity.rect(doc.active_layer_id, 5.0, 5.0, 2.0, 2.0),
    ]
    view.editor.import_entities(entities)
    assert len(doc.entities) == 2
    view.cad_scene.undo_stack.undo()
    assert len(doc.entities) == 0


def test_import_entities_selects_them(view) -> None:
    doc = view.cad_scene.document
    entities = [PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)]
    view.editor.import_entities(entities, select=True)
    selected = view.editor.selected_entities()
    assert len(selected) == 1


def test_import_entities_empty_is_noop(view) -> None:
    assert view.editor.import_entities([]) == 0