"""Test dell'importatore DXF (Step 9i-b/9i-b2/9i-b3)."""

from __future__ import annotations

import math
from pathlib import Path

import ezdxf
import pytest

from lasercontrolsuite.cad.io.dxf_importer import (
    SPLINE_MAX_SEGMENTS,
    import_dxf,
)
from lasercontrolsuite.core.entities import (
    CircleEntity,
    PolylineEntity,
)
from lasercontrolsuite.core.path import PathEntity


def _new_doc(insunits: int = 4):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = insunits
    return doc


def _save(doc, path: Path) -> Path:
    doc.saveas(str(path))
    return path


# =====================================================================
# LINE
# =====================================================================
def test_import_line_basic(tmp_path: Path) -> None:
    doc = _new_doc()
    doc.modelspace().add_line((0, 0), (10, 5))
    p = _save(doc, tmp_path / "line.dxf")

    result = import_dxf(p, layer_id="L1")
    assert len(result.entities) == 1
    e = result.entities[0]
    assert isinstance(e, PolylineEntity)
    assert e.closed is False
    assert e.points == [(0.0, 0.0), (10.0, 5.0)]


# =====================================================================
# LWPOLYLINE
# =====================================================================
def test_import_lwpolyline_open_no_bulge(tmp_path: Path) -> None:
    doc = _new_doc()
    doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 5)], close=False)
    p = _save(doc, tmp_path / "lw.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert e.closed is False
    pts = [n.point for n in e.nodes]
    assert pts == [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]
    assert all(n.is_corner() for n in e.nodes)


def test_import_lwpolyline_closed_no_bulge(tmp_path: Path) -> None:
    doc = _new_doc()
    doc.modelspace().add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)], close=True,
    )
    p = _save(doc, tmp_path / "lw_closed.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert e.closed is True
    assert len(e.nodes) == 4
    assert all(n.is_corner() for n in e.nodes)


def test_import_lwpolyline_with_bulge_produces_bezier(tmp_path: Path) -> None:
    doc = _new_doc()
    doc.modelspace().add_lwpolyline([(0, 0, 1.0), (10, 0, 0.0)], format="xyb")
    p = _save(doc, tmp_path / "lw_bulge.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert len(e.nodes) <= 5
    assert any(n.handle_in is not None or n.handle_out is not None for n in e.nodes)


def test_import_lwpolyline_closed_with_bulge_pocos_nodi(tmp_path: Path) -> None:
    doc = _new_doc()
    doc.modelspace().add_lwpolyline(
        [(0, 0, 1.0), (10, 0, 1.0), (10, 10, 1.0), (0, 10, 1.0)],
        format="xyb", close=True,
    )
    p = _save(doc, tmp_path / "lw_circle.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert e.closed is True
    assert len(e.nodes) <= 15
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, -5.0, abs_tol=0.5)
    assert math.isclose(x1, 15.0, abs_tol=0.5)


# =====================================================================
# POLYLINE (vecchio formato)
# =====================================================================
def test_import_polyline_no_bulge(tmp_path: Path) -> None:
    """POLYLINE senza bulge resta PolylineEntity."""
    doc = _new_doc()
    doc.modelspace().add_polyline2d([(0, 0), (10, 0), (10, 10)], close=False)
    p = _save(doc, tmp_path / "poly.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PolylineEntity)
    assert len(e.points) == 3


def test_import_polyline_with_bulge_produces_bezier(tmp_path: Path) -> None:
    """POLYLINE con bulge → PathEntity con Bézier."""
    doc = _new_doc()
    msp = doc.modelspace()
    poly = msp.add_polyline2d(
        [(0, 0), (10, 0)], format="xyb", close=False,
    )
    poly.vertices[0].dxf.bulge = 1.0
    p = _save(doc, tmp_path / "poly_bulge.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert len(e.nodes) <= 5
    assert any(n.handle_in is not None or n.handle_out is not None for n in e.nodes)


def test_import_polyline_exploded_circle_fits_to_bezier(tmp_path: Path) -> None:
    """POLYLINE con 50 vertici lungo un cerchio → fit → PathEntity chiuso con pochi nodi.

    Un cerchio "esploso" in 50 segmenti dal CAD di origine deve essere
    riconosciuto come arco (fit circolare) e ricostruito con Bézier native.
    """
    doc = _new_doc()
    msp = doc.modelspace()
    pts = [(10 * math.cos(2 * math.pi * i / 50),
            10 * math.sin(2 * math.pi * i / 50)) for i in range(50)]
    msp.add_polyline2d(pts, close=True)
    p = _save(doc, tmp_path / "poly_circle.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    # Fit riuscito → PathEntity chiuso con pochi nodi
    assert isinstance(e, PathEntity)
    assert e.closed is True
    assert len(e.nodes) <= 6
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, -10.0, abs_tol=0.5)
    assert math.isclose(x1, 10.0, abs_tol=0.5)
    assert math.isclose(y0, -10.0, abs_tol=0.5)
    assert math.isclose(y1, 10.0, abs_tol=0.5)
    assert not any("fit circolare non riuscito" in w for w in result.warnings)


# =====================================================================
# CIRCLE / ARC / ELLIPSE
# =====================================================================
def test_import_circle(tmp_path: Path) -> None:
    doc = _new_doc()
    doc.modelspace().add_circle((5, 5), radius=3)
    p = _save(doc, tmp_path / "circle.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, CircleEntity)
    assert math.isclose(e.cx, 5.0, abs_tol=1e-6)
    assert math.isclose(e.cy, 5.0, abs_tol=1e-6)
    assert math.isclose(e.r, 3.0, abs_tol=1e-6)


def test_import_arc_is_bezier(tmp_path: Path) -> None:
    doc = _new_doc()
    doc.modelspace().add_arc(center=(0, 0), radius=10, start_angle=0, end_angle=90)
    p = _save(doc, tmp_path / "arc.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert len(e.nodes) <= 3
    first = e.nodes[0].point
    last = e.nodes[-1].point
    assert math.isclose(first[0], 10.0, abs_tol=1e-3)
    assert math.isclose(first[1], 0.0, abs_tol=1e-3)
    assert math.isclose(last[0], 0.0, abs_tol=1e-3)
    assert math.isclose(last[1], 10.0, abs_tol=1e-3)


def test_import_full_arc_is_closed_with_few_nodes(tmp_path: Path) -> None:
    doc = _new_doc()
    doc.modelspace().add_arc(center=(0, 0), radius=10, start_angle=0, end_angle=360)
    p = _save(doc, tmp_path / "arc360.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert e.closed is True
    assert len(e.nodes) <= 6


def test_import_ellipse_full_is_bezier(tmp_path: Path) -> None:
    doc = _new_doc()
    doc.modelspace().add_ellipse(
        center=(0, 0), major_axis=(10, 0), ratio=0.5,
        start_param=0, end_param=2 * math.pi,
    )
    p = _save(doc, tmp_path / "ellipse.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert e.closed is True
    assert len(e.nodes) <= 6
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, -10.0, abs_tol=0.5)
    assert math.isclose(x1, 10.0, abs_tol=0.5)


# =====================================================================
# SPLINE
# =====================================================================
def test_import_spline_reasonable_density(tmp_path: Path) -> None:
    """SPLINE: cap a SPLINE_MAX_SEGMENTS nodi via fit o decomposizione."""
    doc = _new_doc(insunits=4)
    doc.modelspace().add_spline(
        fit_points=[(0, 0), (30, 20), (60, 0), (100, 30)],
    )
    p = _save(doc, tmp_path / "spline.dxf")

    result = import_dxf(p, layer_id="L1")
    assert len(result.entities) == 1
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert len(e.nodes) <= SPLINE_MAX_SEGMENTS + 1


def test_import_spline_complex_capped(tmp_path: Path) -> None:
    """SPLINE complessa → cap a SPLINE_MAX_SEGMENTS nodi (fit Hermite)."""
    doc = _new_doc(insunits=4)
    pts = [(i * 3.0, 20.0 * math.sin(i * 0.5)) for i in range(30)]
    doc.modelspace().add_spline(fit_points=pts)
    p = _save(doc, tmp_path / "spline_complex.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert len(e.nodes) <= SPLINE_MAX_SEGMENTS + 1
    assert any(n.handle_in is not None or n.handle_out is not None for n in e.nodes)


def test_import_spline_inches_density_consistent(tmp_path: Path) -> None:
    doc = _new_doc(insunits=1)
    doc.modelspace().add_spline(
        fit_points=[(0, 0), (1.2, 0.8), (2.4, 0), (3.94, 1.2)],
    )
    p = _save(doc, tmp_path / "spline_inch.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    x0, y0, x1, y1 = e.world_bounding_box()
    assert 95.0 <= (x1 - x0) <= 105.0
    assert len(e.nodes) <= SPLINE_MAX_SEGMENTS + 1


# =====================================================================
# INSERT
# =====================================================================
def test_import_insert_no_double_transform(tmp_path: Path) -> None:
    doc = _new_doc()
    blk = doc.blocks.new(name="BLK")
    blk.add_line((0, 0), (10, 0))
    doc.modelspace().add_blockref("BLK", insert=(100, 50))
    p = _save(doc, tmp_path / "insert.dxf")

    result = import_dxf(p, layer_id="L1")
    assert len(result.entities) == 1
    e = result.entities[0]
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, 100.0, abs_tol=1e-6)
    assert math.isclose(x1, 110.0, abs_tol=1e-6)
    assert math.isclose(y0, 50.0, abs_tol=1e-6)
    assert math.isclose(y1, 50.0, abs_tol=1e-6)


def test_import_insert_with_scale_and_rotation(tmp_path: Path) -> None:
    doc = _new_doc()
    blk = doc.blocks.new(name="BLK2")
    blk.add_line((0, 0), (10, 0))
    doc.modelspace().add_blockref(
        "BLK2", insert=(0, 0),
        dxfattribs={"xscale": 2, "yscale": 2, "rotation": 90},
    )
    p = _save(doc, tmp_path / "insert_rs.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, 0.0, abs_tol=1e-6)
    assert math.isclose(x1, 0.0, abs_tol=1e-6)
    assert math.isclose(y0, 0.0, abs_tol=1e-6)
    assert math.isclose(y1, 20.0, abs_tol=1e-6)


# =====================================================================
# Unità / edge
# =====================================================================
def test_import_units_inches(tmp_path: Path) -> None:
    doc = _new_doc(insunits=1)
    doc.modelspace().add_line((0, 0), (1, 0))
    p = _save(doc, tmp_path / "inch.dxf")

    result = import_dxf(p, layer_id="L1")
    assert result.unit_scale == 25.4
    e = result.entities[0]
    assert math.isclose(e.points[1][0], 25.4, abs_tol=1e-9)


def test_import_nonexistent_file() -> None:
    with pytest.raises(FileNotFoundError):
        import_dxf("/nonexistent/file.dxf", layer_id="L1")


def test_import_empty_file(tmp_path: Path) -> None:
    doc = _new_doc()
    p = _save(doc, tmp_path / "empty.dxf")
    result = import_dxf(p, layer_id="L1")
    assert result.entities == []


# =====================================================================
# Regressione 9i-b3: fit circolare su POLYLINE esplose
# =====================================================================
def test_import_polyline_exploded_arc_fits_to_bezier(tmp_path: Path) -> None:
    """POLYLINE con 50 vertici lungo un arco (senza bulge) → fit → pochi nodi."""
    doc = _new_doc()
    msp = doc.modelspace()
    pts = [
        (40.0 * math.cos(math.radians(i * 90.0 / 49)),
         40.0 * math.sin(math.radians(i * 90.0 / 49)))
        for i in range(50)
    ]
    msp.add_polyline2d(pts, close=False)
    p = _save(doc, tmp_path / "arc_exploded.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PathEntity)
    assert len(e.nodes) <= 6
    first = e.nodes[0].point
    last = e.nodes[-1].point
    assert math.isclose(first[0], 40.0, abs_tol=0.1)
    assert math.isclose(first[1], 0.0, abs_tol=0.1)
    assert math.isclose(last[0], 0.0, abs_tol=0.1)
    assert math.isclose(last[1], 40.0, abs_tol=0.1)


def test_import_polyline_non_arc_keeps_warning(tmp_path: Path) -> None:
    """POLYLINE a zig-zag con molti vertici (non arco) → warning, resta PolylineEntity."""
    doc = _new_doc()
    msp = doc.modelspace()
    pts = [(float(i), float((i % 2) * 5)) for i in range(40)]
    msp.add_polyline2d(pts, close=False)
    p = _save(doc, tmp_path / "zigzag.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    assert isinstance(e, PolylineEntity)
    assert len(e.points) == 40
    # Il messaggio ora è: "non riconosciuta come curva (fit circolare e fit Bézier falliti)"
    assert any("non riconosciuta come curva" in w for w in result.warnings)

def test_import_polyline_exploded_curve_fits_to_bezier(tmp_path: Path) -> None:
    """Polilinea esplosa che NON è un cerchio (es. curva a S) → fit Bézier."""
    doc = _new_doc()
    msp = doc.modelspace()
    # Una curva a S (polilinea con 30 vertici)
    pts = []
    for i in range(30):
        x = i * 2.0
        y = 20.0 * math.sin(i * 0.2)
        pts.append((x, y))
    msp.add_polyline2d(pts, close=False)
    p = _save(doc, tmp_path / "curve_s.dxf")

    result = import_dxf(p, layer_id="L1")
    e = result.entities[0]
    # Deve aver riconosciuto la curva come Bézier (pochi nodi, non 30)
    assert isinstance(e, PathEntity)
    assert len(e.nodes) <= 10
    assert any(n.handle_in is not None or n.handle_out is not None for n in e.nodes)