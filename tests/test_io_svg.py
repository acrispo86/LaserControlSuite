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
    # Il rect (10,10)-(40,30) in SVG ha Y-down; dopo il flip:
    # top-left SVG (10,10) → (10, 40) in scena; bottom-right → (40, 20)
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
    # Il primo nodo ha handle_out (è una curva)
    assert e.nodes[0].handle_out is not None


def test_import_svg_nonexistent_file() -> None:
    with pytest.raises(FileNotFoundError):
        import_svg("/nonexistent/file.svg", layer_id="L1")


def test_import_svg_y_flip(tmp_path: Path) -> None:
    """Un punto in alto nell'SVG deve risultare in alto (Y alto) nella scena."""
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
    # Il rect in alto a sinistra dell'SVG (0,0)-(10,10) ha y nel range
    # [90, 100] dopo flip (perché SVG height = 100)
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