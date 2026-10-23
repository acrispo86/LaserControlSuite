"""Test dell'adapter di tracing immagini.

Nota: questi test richiedono opencv e scikit-image (extra ``[trace]`` e
``[dev]``). Se mancano, i test vengono saltati.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

# Skip se le dipendenze opzionali non sono disponibili
pytest.importorskip("cv2", reason="opencv-python-headless richiesto per il trace")
pytest.importorskip("skimage", reason="scikit-image richiesto per il trace")

from lasercontrolsuite.cad.io.image_importer import (  # noqa: E402
    ImageTraceOptions,
    trace_image_file,
)
from lasercontrolsuite.core.entities import PolylineEntity  # noqa: E402


def _make_test_png(path: Path, w: int = 200, h: int = 200) -> None:
    """Crea un PNG con un rettangolo nero su fondo bianco."""
    from PIL import Image, ImageDraw

    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 160, 120], fill=0)
    img.save(str(path))


def test_trace_outline_creates_polyline(tmp_path: Path) -> None:
    p = tmp_path / "rect.png"
    _make_test_png(p)

    opts = ImageTraceOptions(mode="outline", dpi=96.0, epsilon=1.0)
    result = trace_image_file(p, layer_id="L1", options=opts)

    assert len(result.entities) >= 1
    assert result.n_outlines >= 1
    assert result.width_mm > 0
    assert result.height_mm > 0


def test_trace_converts_px_to_mm_using_dpi(tmp_path: Path) -> None:
    p = tmp_path / "rect.png"
    _make_test_png(p, w=96, h=96)

    opts = ImageTraceOptions(mode="outline", dpi=96.0, epsilon=1.0)
    result = trace_image_file(p, layer_id="L1", options=opts)

    # 96 px a 96 dpi = 1 pollice = 25.4 mm
    assert math.isclose(result.width_mm, 25.4, abs_tol=0.01)
    assert math.isclose(result.height_mm, 25.4, abs_tol=0.01)


def test_trace_y_flip(tmp_path: Path) -> None:
    """Il rettangolo in alto nell'immagine risulta in alto nella scena."""
    p = tmp_path / "rect_top.png"
    from PIL import Image, ImageDraw

    img = Image.new("L", (100, 100), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 50, 30], fill=0)  # parte alta dell'immagine
    img.save(str(p))

    opts = ImageTraceOptions(mode="outline", dpi=96.0, epsilon=1.0)
    result = trace_image_file(p, layer_id="L1", options=opts)
    assert len(result.entities) >= 1

    # Il bbox dell'entità deve essere nella parte alta (Y alto) della scena
    x0, y0, x1, y1 = result.bounds()
    # L'immagine è 100 px a 96 dpi → ~26.5 mm
    # Il rettangolo è tra y=10 e y=30 px (in alto), che dopo flip è tra
    # y = (100-30)*mm_per_px e (100-10)*mm_per_px
    mm_per_px = 25.4 / 96.0
    expected_y_min = (100 - 30) * mm_per_px
    expected_y_max = (100 - 10) * mm_per_px
    assert math.isclose(y0, expected_y_min, abs_tol=1.5)
    assert math.isclose(y1, expected_y_max, abs_tol=1.5)


def test_trace_nonexistent_file() -> None:
    with pytest.raises(FileNotFoundError):
        trace_image_file("/nonexistent/img.png", layer_id="L1")


def test_trace_centerline_mode(tmp_path: Path) -> None:
    p = tmp_path / "line.png"
    from PIL import Image, ImageDraw

    # Linea spessa orizzontale
    img = Image.new("L", (200, 40), 255)
    d = ImageDraw.Draw(img)
    d.line([(10, 20), (190, 20)], fill=0, width=5)
    img.save(str(p))

    opts = ImageTraceOptions(mode="centerline", dpi=96.0, epsilon=0.5)
    result = trace_image_file(p, layer_id="L1", options=opts)
    assert result.n_centerlines >= 1
    assert len(result.entities) >= 1


def test_trace_entities_have_layer(tmp_path: Path) -> None:
    p = tmp_path / "rect.png"
    _make_test_png(p)
    opts = ImageTraceOptions(mode="outline", dpi=96.0)
    result = trace_image_file(p, layer_id="TRACE_LAYER", options=opts)
    for e in result.entities:
        assert e.layer_id == "TRACE_LAYER"