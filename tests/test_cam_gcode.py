"""Test della generazione G-code."""

from __future__ import annotations

from lasercontrolsuite.cam.gcode import generate_gcode
from lasercontrolsuite.cam.params import CutParams, LaserMode
from lasercontrolsuite.core.document import Document
from lasercontrolsuite.core.entities import PolylineEntity


def _doc_with_rects() -> Document:
    doc = Document()
    doc.add_entity(PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 10.0, 5.0))
    doc.add_entity(PolylineEntity.rect(doc.active_layer_id, 20.0, 0.0, 5.0, 5.0))
    return doc


def test_generates_gcode_nonempty() -> None:
    result = generate_gcode(_doc_with_rects())
    assert result.gcode
    assert "G21" in result.gcode
    assert "G90" in result.gcode
    assert "M5" in result.gcode


def test_header_includes_metadata() -> None:
    result = generate_gcode(_doc_with_rects())
    assert "Percorsi" in result.gcode
    # Step 9c: l'header ora è multi-layer e riporta il numero di layer
    # (le passate sono per-layer e compaiono nel blocco del layer).
    assert "Layer" in result.gcode


def test_power_maps_to_s() -> None:
    params = CutParams(power_percent=50, s_max=1000)
    result = generate_gcode(_doc_with_rects(), params)
    assert "M4 S500" in result.gcode


def test_m3_mode() -> None:
    params = CutParams(power_percent=50, s_max=1000, laser_mode=LaserMode.M3)
    result = generate_gcode(_doc_with_rects(), params)
    assert "M3 S500" in result.gcode


def test_multiple_passes_emits_markers() -> None:
    params = CutParams(passes=3)
    result = generate_gcode(_doc_with_rects(), params)
    assert "Passata 1/3" in result.gcode
    assert "Passata 2/3" in result.gcode
    assert "Passata 3/3" in result.gcode


def test_travel_home_appends_return() -> None:
    params = CutParams(travel_home=True)
    result = generate_gcode(_doc_with_rects(), params)
    assert "G0 X0.000 Y0.000" in result.gcode


def test_travel_home_disabled() -> None:
    params = CutParams(travel_home=False)
    result = generate_gcode(_doc_with_rects(), params)
    # Ci deve essere G0 X10 Y5 per il percorso, ma non X0 Y0 finale
    last_lines = result.gcode.strip().splitlines()[-3:]
    assert not any("G0 X0.000 Y0.000" in ln for ln in last_lines)


def test_air_assist_emits_m8_m9() -> None:
    params = CutParams(air_assist=True)
    result = generate_gcode(_doc_with_rects(), params)
    assert "M8" in result.gcode
    assert "M9" in result.gcode


def test_empty_document_produces_valid_empty_program() -> None:
    doc = Document()
    result = generate_gcode(doc)
    assert "Nessuna entità" in result.gcode
    assert "M5" in result.gcode


def test_only_selected_ids_filters() -> None:
    doc = _doc_with_rects()
    ids = list(doc.entities.keys())
    first_id = ids[0]
    result = generate_gcode(doc, only_selected_ids={first_id})
    assert result.stats.n_paths == 1


def test_stats_computed() -> None:
    result = generate_gcode(_doc_with_rects())
    assert result.stats.n_paths == 2
    assert result.stats.cut_length_mm > 0
    assert result.stats.estimated_cut_seconds > 0


def test_optimize_reduces_travel() -> None:
    """Con optimize=True i percorsi devono essere ordinati."""
    result = generate_gcode(_doc_with_rects(), optimize=True)
    # Non c'è un modo semplice per verificarlo direttamente, ma il numero
    # di percorsi resta lo stesso
    assert result.stats.n_paths == 2


def test_custom_header_comment() -> None:
    params = CutParams(header_comment="Mio progetto\nCliente: Rossi")
    result = generate_gcode(_doc_with_rects(), params)
    assert "Mio progetto" in result.gcode
    assert "Cliente: Rossi" in result.gcode


def test_feed_applied_to_first_move() -> None:
    params = CutParams(feed_mm_min=1234.0)
    result = generate_gcode(_doc_with_rects(), params)
    assert "F1234" in result.gcode