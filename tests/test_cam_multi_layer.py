"""Test della generazione G-code multi-layer (Step 9c)."""
from __future__ import annotations

from lasercontrolsuite.cam.gcode import generate_gcode
from lasercontrolsuite.cam.params import GlobalParams, LaserMode
from lasercontrolsuite.core.document import Document
from lasercontrolsuite.core.entities import PolylineEntity
from lasercontrolsuite.core.layer import Layer


def _doc_two_layers() -> Document:
    doc = Document()
    # Layer di default (Layer 1)
    l1 = list(doc.layers.values())[0]
    l1.power_percent = 30
    l1.speed_mm_min = 800
    l1.passes = 1
    # Secondo layer
    l2 = Layer.new("Layer 2", priority=1)
    l2.power_percent = 80
    l2.speed_mm_min = 400
    l2.passes = 2
    doc.add_layer(l2)

    e1 = PolylineEntity.rect(l1.id, 0.0, 0.0, 10.0, 5.0)
    e2 = PolylineEntity.rect(l2.id, 20.0, 0.0, 5.0, 5.0)
    e1.layer_id = l1.id
    e2.layer_id = l2.id
    doc.add_entity(e1)
    doc.add_entity(e2)
    return doc


def test_generate_multi_layer_produces_two_blocks():
    doc = _doc_two_layers()
    result = generate_gcode(doc, GlobalParams())
    assert "Layer 1: Layer 1" in result.gcode
    assert "Layer 2: Layer 2" in result.gcode
    assert result.stats.n_paths == 2
    assert len(result.layer_stats) == 2


def test_generate_layer_params_applied():
    doc = _doc_two_layers()
    result = generate_gcode(doc, GlobalParams(s_max=1000, laser_mode=LaserMode.M4))
    # Layer 1: power 30% → S300; Layer 2: power 80% → S800
    assert "M4 S300" in result.gcode
    assert "M4 S800" in result.gcode
    # Layer 2 ha 2 passate → marker
    assert "Passata 1/2" in result.gcode
    assert "Passata 2/2" in result.gcode


def test_generate_legacy_cutparams_applies_to_all():
    """Passando un CutParams, il comportamento resta quello pre-9c."""
    from lasercontrolsuite.cam.params import CutParams
    doc = _doc_two_layers()
    params = CutParams(power_percent=50, s_max=1000, passes=1)
    result = generate_gcode(doc, params)
    # Il layer 2 avrebbe S800 se letto dal layer; con legacy è S500
    assert "M4 S500" in result.gcode
    assert "M4 S800" not in result.gcode


def test_layer_priority_orders_blocks():
    doc = Document()
    l1 = list(doc.layers.values())[0]
    l1.priority = 10
    l1.name = "Tardi"
    l2 = Layer.new("Prima", priority=1)
    doc.add_layer(l2)

    e1 = PolylineEntity.rect(l1.id, 0.0, 0.0, 1.0, 1.0)
    e2 = PolylineEntity.rect(l2.id, 10.0, 0.0, 1.0, 1.0)
    e1.layer_id = l1.id
    e2.layer_id = l2.id
    doc.add_entity(e1)
    doc.add_entity(e2)

    result = generate_gcode(doc, GlobalParams())
    gcode = result.gcode
    # "Prima" deve apparire prima di "Tardi"
    assert gcode.index("Prima") < gcode.index("Tardi")


def test_layer_breakdown_stats():
    doc = _doc_two_layers()
    result = generate_gcode(doc, GlobalParams())
    names = [ls.layer_name for ls in result.layer_stats]
    assert "Layer 1" in names
    assert "Layer 2" in names
    for ls in result.layer_stats:
        assert ls.cut_length_mm > 0
        assert ls.s_value >= 0
        assert ls.n_passes >= 1