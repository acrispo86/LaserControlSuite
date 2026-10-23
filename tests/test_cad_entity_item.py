"""Test dell'EntityItem."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from lasercontrolsuite.core.document import Document  # noqa: E402
from lasercontrolsuite.core.entities import PolylineEntity, TextEntity  # noqa: E402
from lasercontrolsuite.core.matrix import Matrix2D  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    from lasercontrolsuite.app import get_or_create_qapplication

    return get_or_create_qapplication([])


# =====================================================================
# Snap points
# =====================================================================
def test_item_snap_points_in_scene_coordinates(qapp: QApplication) -> None:
    from lasercontrolsuite.cad.entity_item import EntityItem

    doc = Document()
    e = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 10.0, 0.0)
    e.transform = Matrix2D.translation(100.0, 50.0)
    doc.add_entity(e)

    scene = QGraphicsScene()
    item = EntityItem(e, doc)
    scene.addItem(item)

    pts = item.snap_points()
    xs = sorted(p.x() for p in pts)
    ys = sorted(p.y() for p in pts)
    assert math.isclose(xs[0], 100.0, abs_tol=1e-9)
    assert math.isclose(xs[-1], 110.0, abs_tol=1e-9)
    assert all(math.isclose(y, 50.0, abs_tol=1e-9) for y in ys)


# =====================================================================
# Sincronizzazione con il documento
# =====================================================================
def test_item_syncs_when_entity_changes(qapp: QApplication) -> None:
    from lasercontrolsuite.cad.entity_item import EntityItem

    doc = Document()
    e = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    doc.add_entity(e)

    scene = QGraphicsScene()
    item = EntityItem(e, doc)
    scene.addItem(item)

    doc.update_entity_transform(e.id, Matrix2D.translation(5.0, 5.0))
    item.sync_from_entity()

    assert math.isclose(item.transform().dx(), 5.0, abs_tol=1e-9)
    assert math.isclose(item.transform().dy(), 5.0, abs_tol=1e-9)


# =====================================================================
# Bounding rect
# =====================================================================
def test_item_bounding_rect_covers_geometry(qapp: QApplication) -> None:
    from lasercontrolsuite.cad.entity_item import EntityItem

    doc = Document()
    e = PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 4.0, 3.0)
    doc.add_entity(e)

    scene = QGraphicsScene()
    item = EntityItem(e, doc)
    scene.addItem(item)

    r = item.boundingRect()
    assert r.width() >= 4.0
    assert r.height() >= 3.0


# =====================================================================
# Testo: dritto (Y-up), dimensionato in mm reali
# =====================================================================
def _text_path_height(text: str, font_size_mm: float) -> float:
    from lasercontrolsuite.cad.entity_item import EntityItem

    doc = Document()
    t = TextEntity(layer_id=doc.active_layer_id, text=text, font_size_mm=font_size_mm)
    doc.add_entity(t)

    scene = QGraphicsScene()
    item = EntityItem(t, doc)
    scene.addItem(item)

    r = item._build_local_path().boundingRect()
    return r.height(), r


def test_text_path_develops_upward(qapp: QApplication) -> None:
    """Il path del testo deve svilupparsi verso Y positivo (Y-up) e in mm reali.

    Regressione storica: il path di ``QPainterPath.addText`` è in convenzione
    Qt (Y-down, pixel). Senza flip Y + scala mm/px, il testo appare capovolto
    e con dimensioni errate.
    """
    h, r = _text_path_height("A", font_size_mm=10.0)

    assert h > 0, "Il path del testo è vuoto"
    assert r.top() >= -0.1, (
        f"Il testo sporge sotto la baseline (top={r.top():.3f}). "
        "Probabilmente manca la flip Y."
    )
    assert r.bottom() > 0, (
        f"Il testo non sale sopra la baseline (bottom={r.bottom():.3f}). "
        "Probabilmente è capovolto."
    )
    # Con la conversione corretta, il cap-height di "A" per un font 10 mm
    # è tipicamente tra il 60% e il 100% di 10 mm. Range ampio per tollerare
    # differenze tra font e DPI.
    assert 4.0 <= h <= 14.0, (
        f"Altezza anomala: {h:.3f} mm (attesa ~10 mm, ordine di grandezza di "
        "font_size_mm). Probabilmente manca la scala mm/px."
    )


def test_text_height_scales_linearly(qapp: QApplication) -> None:
    """Raddoppiare ``font_size_mm`` deve raddoppiare l'altezza del path.

    Questo test è robusto al DPI effettivo: verifica solo la linearità.
    """
    h10, _ = _text_path_height("A", 10.0)
    h20, _ = _text_path_height("A", 20.0)
    assert h10 > 0
    assert math.isclose(h20 / h10, 2.0, rel_tol=0.05), (
        f"Scala non lineare: h(10)={h10:.3f}, h(20)={h20:.3f}"
    )


def test_text_bbox_is_centered_on_baseline_x(qapp: QApplication) -> None:
    """Il testo parte da x=0 (baseline sinistra) e si sviluppa in x positivo."""
    _, r = _text_path_height("Hello", 10.0)
    assert r.left() >= -0.1
    assert r.right() > 0


def test_text_item_has_positive_height(qapp: QApplication) -> None:
    """Il bounding rect dell'item di testo deve avere altezza sensata."""
    from lasercontrolsuite.cad.entity_item import EntityItem

    doc = Document()
    t = TextEntity(layer_id=doc.active_layer_id, text="Hello", font_size_mm=10.0)
    doc.add_entity(t)

    scene = QGraphicsScene()
    item = EntityItem(t, doc)
    scene.addItem(item)

    r = item.boundingRect()
    assert r.height() > 1.0
    assert r.width() > 1.0