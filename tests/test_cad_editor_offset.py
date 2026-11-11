"""Test per ``CanvasEditor.offset_selection`` (Step 9g)."""

from __future__ import annotations

import pytest

from lasercontrolsuite.cad.editor import CanvasEditor
from lasercontrolsuite.cad.view import CadGraphicsView
from lasercontrolsuite.cad.commands import AddEntitiesCommand
from lasercontrolsuite.core.entities import PolylineEntity
from lasercontrolsuite.core.offset_ops import OffsetJoinStyle, OffsetMode


def _square(size: float = 10.0, layer_id: str = "L1") -> PolylineEntity:
    return PolylineEntity(
        points=[(0.0, 0.0), (size, 0.0), (size, size), (0.0, size)],
        closed=True,
        layer_id=layer_id,
    )


def _add_and_select(view, entity) -> None:
    view.cad_scene.undo_stack.push(
        AddEntitiesCommand(view.cad_scene.document, [entity], "test")
    )
    item = view.cad_scene.entity_item(entity.id)
    assert item is not None
    item.setSelected(True)


@pytest.fixture
def view(qtbot):
    v = CadGraphicsView()
    qtbot.addWidget(v)
    return v


def test_offset_replaces_selection(view):
    editor = CanvasEditor(view)
    sq = _square()
    _add_and_select(view, sq)

    n, warnings = editor.offset_selection(
        1.0, OffsetMode.OUTSET, OffsetJoinStyle.ROUND
    )
    assert n == 1
    assert warnings == []
    # L'originale è sparito
    assert view.cad_scene.entity_item(sq.id) is None
    # C'è una nuova entità
    assert len(editor.selected_entities()) == 1


def test_offset_is_undoable(view):
    editor = CanvasEditor(view)
    sq = _square()
    _add_and_select(view, sq)

    editor.offset_selection(1.0, OffsetMode.OUTSET, OffsetJoinStyle.ROUND)
    assert view.cad_scene.entity_item(sq.id) is None

    view.cad_scene.undo_stack.undo()
    # L'originale è tornato
    assert view.cad_scene.entity_item(sq.id) is not None


def test_offset_no_selection_returns_warning(view):
    editor = CanvasEditor(view)
    n, warnings = editor.offset_selection(1.0)
    assert n == 0
    assert warnings


def test_offset_failure_does_not_modify_document(view):
    editor = CanvasEditor(view)
    sq = _square()
    _add_and_select(view, sq)

    n, warnings = editor.offset_selection(
        100.0, OffsetMode.INSET, OffsetJoinStyle.ROUND
    )
    assert n == 0
    assert warnings
    # L'entità originale è ancora lì
    assert view.cad_scene.entity_item(sq.id) is not None