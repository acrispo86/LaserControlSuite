"""Test per la conversione testo → path (Step 9h)."""

from __future__ import annotations

import pytest

from lasercontrolsuite.cad.editor import CanvasEditor
from lasercontrolsuite.cad.text_to_path import text_entity_to_paths
from lasercontrolsuite.cad.view import CadGraphicsView
from lasercontrolsuite.cad.commands import AddEntitiesCommand
from lasercontrolsuite.core.entities import PolylineEntity, TextEntity
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.path import PathEntity


@pytest.fixture
def view(qtbot):
    v = CadGraphicsView()
    qtbot.addWidget(v)
    return v


def test_single_letter_produces_paths():
    text = TextEntity(text="A", layer_id="L1", font_size_mm=10.0)
    paths = text_entity_to_paths(text)
    assert paths is not None
    assert len(paths) >= 1
    # La "A" ha almeno un contorno esterno + foro
    for p in paths:
        assert isinstance(p, PathEntity)
        assert len(p.nodes) >= 2
        assert p.layer_id == "L1"


def test_multi_letter_produces_multiple_paths():
    text = TextEntity(text="AB", layer_id="L1", font_size_mm=10.0)
    paths = text_entity_to_paths(text)
    assert paths is not None
    # "AB" ha almeno 2 subpath chiusi (spesso di più per i fori)
    assert len(paths) >= 2


def test_empty_text_returns_none():
    assert text_entity_to_paths(TextEntity(text="")) is None


def test_transform_preserved():
    text = TextEntity(text="A", layer_id="L1", font_size_mm=10.0)
    text.transform = Matrix2D.translation(5.0, 7.0) @ Matrix2D.rotation_deg(30.0)
    paths = text_entity_to_paths(text)
    assert paths
    # Verifica la matrice tramite due punti non collineari (origine + asse X):
    # se le due trasformazioni producono gli stessi risultati sui due punti,
    # sono la stessa matrice affine 2D.
    origin = text.transform.transform_point(0.0, 0.0)
    unit_x = text.transform.transform_point(1.0, 0.0)
    for p in paths:
        assert p.transform.transform_point(0.0, 0.0) == pytest.approx(origin)
        assert p.transform.transform_point(1.0, 0.0) == pytest.approx(unit_x)


def test_letter_o_has_closed_path():
    text = TextEntity(text="O", layer_id="L1", font_size_mm=10.0)
    paths = text_entity_to_paths(text)
    assert paths
    # "O" produce contorno esterno + foro, entrambi chiusi
    assert any(p.closed for p in paths)


# ---------------------------------------------------------------- editor
def _add_and_select(view, entity) -> None:
    view.cad_scene.undo_stack.push(
        AddEntitiesCommand(view.cad_scene.document, [entity], "test")
    )
    item = view.cad_scene.entity_item(entity.id)
    assert item is not None
    item.setSelected(True)


def test_editor_converts_text_entity(view):
    editor = CanvasEditor(view)
    text = TextEntity(text="A", layer_id="L1", font_size_mm=10.0)
    _add_and_select(view, text)

    n = editor.convert_selection_to_path()
    assert n == 1
    # Il TextEntity è sparito
    assert view.cad_scene.entity_item(text.id) is None
    # C'è almeno un PathEntity selezionato
    selected = editor.selected_entities()
    assert len(selected) >= 1
    assert all(isinstance(e, PathEntity) for e in selected)


def test_editor_convert_text_is_undoable(view):
    editor = CanvasEditor(view)
    text = TextEntity(text="A", layer_id="L1", font_size_mm=10.0)
    _add_and_select(view, text)

    editor.convert_selection_to_path()
    assert view.cad_scene.entity_item(text.id) is None

    view.cad_scene.undo_stack.undo()
    # Il testo originale è tornato
    assert view.cad_scene.entity_item(text.id) is not None


def test_editor_convert_mixed_selection(view):
    editor = CanvasEditor(view)
    text = TextEntity(text="A", layer_id="L1", font_size_mm=10.0)
    rect = PolylineEntity.rect("L1", 0.0, 0.0, 5.0, 3.0)
    view.cad_scene.undo_stack.push(
        AddEntitiesCommand(view.cad_scene.document, [text, rect], "test")
    )
    for eid in (text.id, rect.id):
        item = view.cad_scene.entity_item(eid)
        assert item is not None
        item.setSelected(True)

    n = editor.convert_selection_to_path()
    # 1 text + 1 rect convertiti
    assert n == 2
    assert view.cad_scene.entity_item(text.id) is None
    assert view.cad_scene.entity_item(rect.id) is not None  # id preservato
    # Il rettangolo è ora un PathEntity
    converted = view.cad_scene.document.get_entity(rect.id)
    assert isinstance(converted, PathEntity)