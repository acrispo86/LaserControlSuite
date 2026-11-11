"""Test dell'importatore SVG."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from lasercontrolsuite.cad.io.svg_importer import import_svg
from lasercontrolsuite.core.entities import (
    CircleEntity,
    EllipseEntity,
    PolylineEntity,
)
from lasercontrolsuite.core.path import PathEntity


def _write_svg(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# =====================================================================
# Base
# =====================================================================
def test_import_svg_mm_dimensions(tmp_path: Path) -> None:
    p = tmp_path / "test.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm"
     viewBox="0 0 100 50">
  <rect x="10" y="10" width="30" height="20"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    assert math.isclose(result.width_mm, 100.0, abs_tol=1e-6)
    assert math.isclose(result.height_mm, 50.0, abs_tol=1e-6)
    assert len(result.entities) == 1
    e = result.entities[0]
    assert isinstance(e, PolylineEntity)
    assert e.closed is True
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, 10.0, abs_tol=0.1)
    assert math.isclose(x1, 40.0, abs_tol=0.1)
    assert math.isclose(y0, 20.0, abs_tol=0.1)
    assert math.isclose(y1, 40.0, abs_tol=0.1)


def test_import_svg_circle(tmp_path: Path) -> None:
    p = tmp_path / "c.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="20"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    assert len(result.entities) == 1
    c = result.entities[0]
    assert isinstance(c, CircleEntity)
    assert math.isclose(c.r, 20.0, abs_tol=0.1)


def test_import_svg_path_line(tmp_path: Path) -> None:
    p = tmp_path / "path.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <path d="M 10,10 L 90,10 L 90,90 Z"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    assert len(result.entities) == 1
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert e.closed is True


def test_import_svg_path_curve(tmp_path: Path) -> None:
    p = tmp_path / "curve.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <path d="M 10,50 C 30,10 70,90 90,50"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    assert len(result.entities) == 1
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert len(e.nodes) >= 2
    assert e.nodes[0].handle_out is not None


def test_import_svg_nonexistent_file() -> None:
    with pytest.raises(FileNotFoundError):
        import_svg("/nonexistent/file.svg", layer_id="L1")


def test_import_svg_y_flip(tmp_path: Path) -> None:
    p = tmp_path / "flip.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <rect x="0" y="0" width="10" height="10"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    e = result.entities[0]
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(y0, 90.0, abs_tol=0.1)
    assert math.isclose(y1, 100.0, abs_tol=0.1)


def test_import_svg_polygon(tmp_path: Path) -> None:
    p = tmp_path / "poly.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <polygon points="0,0 50,0 50,50"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PolylineEntity)
    assert e.closed is True


# =====================================================================
# Regressione Step 9i-a
# =====================================================================
def test_svg_arc_produces_few_bezier_nodes(tmp_path: Path) -> None:
    """Step 9i-b2: arco SVG circolare → Bézier native, pochi nodi."""
    p = tmp_path / "arc.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <path d="M 10,50 A 40 40 0 0 1 50,10"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    assert len(result.entities) == 1
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    # Arco da ~90° → 1 Bézier → 2-3 nodi (prima erano decine)
    assert len(e.nodes) <= 6


def test_two_subpaths_produce_two_entities(tmp_path: Path) -> None:
    p = tmp_path / "sub.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <path d="M 10,10 L 20,10 M 30,30 L 40,30"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    assert len(result.entities) == 2
    for e in result.entities:
        assert isinstance(e, PathEntity)
        assert len(e.nodes) == 2
        assert e.closed is False


def test_letter_with_hole_produces_two_closed_paths(tmp_path: Path) -> None:
    p = tmp_path / "hole.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <path d="M 10,10 L 20,10 L 20,20 L 10,20 Z
           M 13,13 L 17,13 L 17,17 L 13,17 Z"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    assert len(result.entities) == 2
    for e in result.entities:
        assert isinstance(e, PathEntity)
        assert e.closed is True


def test_closed_path_keeps_first_node_handle(tmp_path: Path) -> None:
    p = tmp_path / "closedcurve.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <path d="M 10,10 C 20,10 30,30 40,10 C 30,50 20,30 10,10"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert e.closed is True
    assert e.nodes[0].handle_out is not None
    assert e.nodes[0].handle_in is not None


def test_three_subpaths_from_single_path(tmp_path: Path) -> None:
    p = tmp_path / "three.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <path d="M 10,10 L 20,10 L 20,20 Z
           M 30,30 L 40,30 L 40,40 Z
           M 50,50 L 60,50 L 60,60 Z"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    assert len(result.entities) == 3
    for e in result.entities:
        assert isinstance(e, PathEntity)
        assert e.closed is True


# =====================================================================
# Transform / viewBox
# =====================================================================
def test_import_svg_path_transform_flip(tmp_path: Path) -> None:
    p = tmp_path / "flip_transform.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 -100 100 100">
  <path transform="matrix(1,0,0,-1,0,0)" d="M 10,90 L 90,90 L 90,10"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    e = result.entities[0]
    first = e.nodes[0].point
    assert math.isclose(first[0], 10.0, abs_tol=0.1)
    assert math.isclose(first[1], 90.0, abs_tol=0.1)


def test_import_svg_group_transform_translate(tmp_path: Path) -> None:
    p = tmp_path / "group.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="0 0 100 100">
  <g transform="translate(20, 10)">
    <rect x="0" y="0" width="10" height="10"/>
  </g>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    e = result.entities[0]
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, 20.0, abs_tol=0.1)
    assert math.isclose(x1, 30.0, abs_tol=0.1)
    assert math.isclose(y0, 80.0, abs_tol=0.1)
    assert math.isclose(y1, 90.0, abs_tol=0.1)


def test_import_svg_viewbox_offset(tmp_path: Path) -> None:
    p = tmp_path / "vb.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm"
     viewBox="-50 -50 100 100">
  <rect x="0" y="0" width="10" height="10"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    e = result.entities[0]
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, 50.0, abs_tol=0.1)
    assert math.isclose(x1, 60.0, abs_tol=0.1)
    assert math.isclose(y0, 40.0, abs_tol=0.1)
    assert math.isclose(y1, 50.0, abs_tol=0.1)


def test_import_svg_real_world_flip_scenario(tmp_path: Path) -> None:
    p = tmp_path / "real.svg"
    _write_svg(p, """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="66.011mm" height="61.320mm"
     viewBox="193.994339 -169.659836 66.011337 61.319656">
  <path transform="matrix(1,0,0,-1,0,0)"
        d="M205.699127,169.640656 L259.921936,144.804703 L228.13887,109.791672 Z"/>
</svg>
""")
    result = import_svg(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    first = e.nodes[0].point
    assert math.isclose(first[0], 11.70, abs_tol=0.2)
    assert math.isclose(first[1], 61.30, abs_tol=0.2)
    x0, y0, x1, y1 = e.world_bounding_box()
    assert -1.0 <= x0 <= 67.0
    assert 0.0 <= y0 <= 62.0