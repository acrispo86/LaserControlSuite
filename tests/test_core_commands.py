"""Test dei comandi undo/redo."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QUndoStack  # noqa: E402

from lasercontrolsuite.core.commands import (  # noqa: E402
    AddEntityCommand,
    RemoveEntityCommand,
    ReplaceEntityCommand,
    TransformEntityCommand,
)
from lasercontrolsuite.core.document import Document  # noqa: E402
from lasercontrolsuite.core.entities import PolylineEntity  # noqa: E402
from lasercontrolsuite.core.matrix import Matrix2D  # noqa: E402
from lasercontrolsuite.core.path import PathEntity, PathNode  # noqa: E402


def _doc() -> Document:
    return Document()


def test_add_entity_command_redo_undo() -> None:
    doc = _doc()
    e = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    stack = QUndoStack()
    stack.push(AddEntityCommand(doc, e))

    assert doc.get_entity(e.id) is e

    stack.undo()
    assert doc.get_entity(e.id) is None

    stack.redo()
    assert doc.get_entity(e.id) is e


def test_remove_entity_command() -> None:
    doc = _doc()
    e = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    doc.add_entity(e)

    stack = QUndoStack()
    stack.push(RemoveEntityCommand(doc, e))
    assert doc.get_entity(e.id) is None

    stack.undo()
    assert doc.get_entity(e.id) is e


def test_transform_command() -> None:
    doc = _doc()
    e = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    doc.add_entity(e)

    target = Matrix2D.translation(10.0, 5.0)
    stack = QUndoStack()
    stack.push(TransformEntityCommand(doc, e.id, target))
    assert e.transform.almost_equals(target)

    stack.undo()
    assert e.transform.is_identity()

    stack.redo()
    assert e.transform.almost_equals(target)


# =====================================================================
# ReplaceEntityCommand
# =====================================================================
def test_replace_entity_command_swaps_type() -> None:
    doc = _doc()
    poly = PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 10.0, 5.0)
    doc.add_entity(poly)

    path = PathEntity(
        id=poly.id,
        layer_id=poly.layer_id,
        nodes=[PathNode((0.0, 0.0)), PathNode((1.0, 0.0))],
        closed=False,
    )

    stack = QUndoStack()
    stack.push(ReplaceEntityCommand(doc, poly, path))

    # Ora c'è il PathEntity
    assert isinstance(doc.get_entity(poly.id), PathEntity)

    stack.undo()
    # Ora di nuovo la PolylineEntity
    assert isinstance(doc.get_entity(poly.id), PolylineEntity)
    assert doc.get_entity(poly.id) is poly

    stack.redo()
    assert isinstance(doc.get_entity(poly.id), PathEntity)


def test_replace_entity_command_requires_same_id() -> None:
    doc = _doc()
    a = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    b = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    import pytest
    with pytest.raises(ValueError):
        ReplaceEntityCommand(doc, a, b)


def test_replace_entity_command_swap_preserves_id() -> None:
    doc = _doc()
    poly = PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 10.0, 5.0)
    doc.add_entity(poly)
    original_id = poly.id

    path = PathEntity(
        id=original_id,
        layer_id=poly.layer_id,
        nodes=[PathNode((0.0, 0.0)), PathNode((1.0, 0.0))],
        closed=False,
    )
    stack = QUndoStack()
    stack.push(ReplaceEntityCommand(doc, poly, path))

    assert doc.get_entity(original_id) is path

    stack.undo()
    assert doc.get_entity(original_id) is poly