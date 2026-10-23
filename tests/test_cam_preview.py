"""Test dell'anteprima CAM."""

from __future__ import annotations

from lasercontrolsuite.cam.flatten import FlatPath
from lasercontrolsuite.cam.preview import build_preview


def _fp(points, closed=False, entity_id="e"):
    return FlatPath(points=list(points), closed=closed, entity_id=entity_id)


def test_preview_paths_match_input() -> None:
    paths = [
        _fp([(0.0, 0.0), (10.0, 0.0)]),
        _fp([(20.0, 0.0), (30.0, 0.0)]),
    ]
    preview = build_preview(paths)
    assert len(preview.cut_paths) == 2
    assert preview.cut_paths[0].order_index == 0
    assert preview.cut_paths[1].order_index == 1


def test_preview_travel_from_origin() -> None:
    paths = [_fp([(10.0, 0.0), (20.0, 0.0)])]
    preview = build_preview(paths, start=(0.0, 0.0))
    # Un solo travel: da (0,0) a (10,0)
    assert len(preview.travel_segments) == 1
    assert preview.travel_segments[0] == ((0.0, 0.0), (10.0, 0.0))


def test_preview_bounds() -> None:
    paths = [_fp([(0.0, 0.0), (100.0, 50.0)])]
    preview = build_preview(paths, include_travel=False)
    x0, y0, x1, y1 = preview.bounds()
    assert (x0, y0, x1, y1) == (0.0, 0.0, 100.0, 50.0)


def test_preview_empty() -> None:
    preview = build_preview([])
    assert preview.cut_paths == []
    assert preview.bounds() == (0.0, 0.0, 0.0, 0.0)