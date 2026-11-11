"""Test per ``core.offset_ops.compute_offset`` (Step 9g)."""

from __future__ import annotations

import pytest

from lasercontrolsuite.core.entities import PolylineEntity, TextEntity
from lasercontrolsuite.core.offset_ops import (
    OffsetJoinStyle,
    OffsetMode,
    compute_offset,
)


def _square(size: float = 10.0, layer_id: str = "L1") -> PolylineEntity:
    return PolylineEntity(
        points=[(0.0, 0.0), (size, 0.0), (size, size), (0.0, size)],
        closed=True,
        layer_id=layer_id,
    )


def _bbox(path):
    return path.world_bounding_box()


# ---------------------------------------------------------------- basic
def test_outset_square_grows():
    sq = _square(10.0)
    paths, warnings = compute_offset([sq], 1.0, OffsetMode.OUTSET)
    assert len(paths) == 1
    assert warnings == []
    x0, y0, x1, y1 = _bbox(paths[0])
    assert (x1 - x0) == pytest.approx(12.0, abs=0.05)
    assert (y1 - y0) == pytest.approx(12.0, abs=0.05)


def test_inset_square_shrinks():
    sq = _square(10.0)
    paths, warnings = compute_offset([sq], 1.0, OffsetMode.INSET)
    assert len(paths) == 1
    assert warnings == []
    x0, y0, x1, y1 = _bbox(paths[0])
    assert (x1 - x0) == pytest.approx(8.0, abs=0.05)
    assert (y1 - y0) == pytest.approx(8.0, abs=0.05)


def test_outset_offset_is_closed_path():
    sq = _square(10.0)
    paths, _ = compute_offset([sq], 1.0, OffsetMode.OUTSET)
    assert paths[0].closed is True


# ---------------------------------------------------------------- edge cases
def test_inset_too_large_yields_empty_with_warning():
    sq = _square(10.0)
    paths, warnings = compute_offset([sq], 100.0, OffsetMode.INSET)
    assert paths == []
    assert any("vuoto" in w.lower() for w in warnings)


def test_zero_distance_warns_and_returns_empty():
    sq = _square(10.0)
    paths, warnings = compute_offset([sq], 0.0, OffsetMode.OUTSET)
    assert paths == []
    assert any("zero" in w.lower() for w in warnings)


def test_negative_distance_warns_and_returns_empty():
    sq = _square(10.0)
    paths, warnings = compute_offset([sq], -1.0, OffsetMode.OUTSET)
    assert paths == []
    assert any(">= 0" in w or "maggiore" in w.lower() for w in warnings)


def test_empty_input_returns_empty():
    paths, warnings = compute_offset([], 1.0)
    assert paths == []
    assert warnings


# ---------------------------------------------------------------- join styles
def test_join_style_mitre_keeps_sharp_corners():
    sq = _square(10.0)
    paths, _ = compute_offset(
        [sq], 1.0, OffsetMode.OUTSET, OffsetJoinStyle.MITRE
    )
    assert len(paths) == 1
    # Anche con mitre, il bbox cresce di ~1mm per lato
    x0, y0, x1, y1 = _bbox(paths[0])
    assert (x1 - x0) == pytest.approx(12.0, abs=0.1)


def test_join_style_bevel_produces_path():
    sq = _square(10.0)
    paths, warnings = compute_offset(
        [sq], 1.0, OffsetMode.OUTSET, OffsetJoinStyle.BEVEL
    )
    assert len(paths) == 1
    assert warnings == []


# ---------------------------------------------------------------- filters
def test_text_entity_skipped_with_warning():
    txt = TextEntity(text="ciao", layer_id="L1")
    sq = _square(10.0)
    paths, warnings = compute_offset([txt, sq], 1.0)
    assert len(paths) == 1
    assert any("non convertibile" in w.lower() for w in warnings)


def test_layer_id_preserved():
    sq = _square(10.0, layer_id="MYLAYER")
    paths, _ = compute_offset([sq], 1.0)
    assert paths
    assert all(p.layer_id == "MYLAYER" for p in paths)


# ---------------------------------------------------------------- multi
def test_two_separate_entities_produce_two_paths():
    a = _square(10.0, layer_id="L1")
    b = PolylineEntity(
        points=[(20.0, 0.0), (30.0, 0.0), (30.0, 10.0), (20.0, 10.0)],
        closed=True,
        layer_id="L1",
    )
    paths, warnings = compute_offset([a, b], 1.0, OffsetMode.OUTSET)
    assert len(paths) == 2
    assert warnings == []