"""Test dell'ordinamento percorsi."""

from __future__ import annotations

import math

from lasercontrolsuite.cam.flatten import FlatPath
from lasercontrolsuite.cam.order import order_paths


def _fp(points, closed=False, entity_id="e"):
    return FlatPath(points=list(points), closed=closed, entity_id=entity_id)


def test_order_simple_nearest_first() -> None:
    a = _fp([(100.0, 100.0), (110.0, 100.0)], entity_id="A")
    b = _fp([(5.0, 5.0), (10.0, 5.0)], entity_id="B")
    ordered = order_paths([a, b], start=(0.0, 0.0))
    # B è più vicino a (0,0)
    assert ordered[0].entity_id == "B"
    assert ordered[1].entity_id == "A"


def test_order_chain() -> None:
    a = _fp([(0.0, 0.0), (10.0, 0.0)], entity_id="A")
    b = _fp([(10.0, 0.0), (20.0, 0.0)], entity_id="B")
    c = _fp([(20.0, 0.0), (30.0, 0.0)], entity_id="C")
    ordered = order_paths([c, a, b], start=(0.0, 0.0))
    assert [p.entity_id for p in ordered] == ["A", "B", "C"]


def test_order_can_reverse_open_path() -> None:
    # Percorso con la coda vicina all'origine; deve essere invertito
    p = _fp([(100.0, 100.0), (0.5, 0.5)], entity_id="P")
    ordered = order_paths([p], start=(0.0, 0.0), allow_reverse=True)
    # Dopo reverse, il primo punto è (0.5, 0.5)
    assert ordered[0].points[0] == (0.5, 0.5)


def test_order_does_not_reverse_closed_path() -> None:
    p = _fp([(100.0, 100.0), (110.0, 100.0), (105.0, 105.0)],
            closed=True, entity_id="P")
    ordered = order_paths([p], start=(0.0, 0.0), allow_reverse=True)
    # Non deve invertire un percorso chiuso
    assert ordered[0].points[0] == (100.0, 100.0)
    assert ordered[0].closed is True


def test_order_empty() -> None:
    assert order_paths([], start=(0.0, 0.0)) == []


def test_order_total_travel_is_reduced() -> None:
    """Confronta il travel totale con e senza ordinamento.

    Layout: due percorsi vicini e uno lontano.
    L'ordinamento deve scegliere di fare prima i due vicini.
    """
    near1 = _fp([(1.0, 0.0), (2.0, 0.0)], entity_id="N1")
    near2 = _fp([(3.0, 0.0), (4.0, 0.0)], entity_id="N2")
    far = _fp([(1000.0, 1000.0), (1010.0, 1000.0)], entity_id="F")

    ordered = order_paths([near1, far, near2], start=(0.0, 0.0))
    ids = [p.entity_id for p in ordered]
    # I due "near" devono venire prima del "far"
    assert ids.index("F") == 2

# =====================================================================
# Step 9c — invariante multi-layer
# =====================================================================
def test_order_preserves_layer_groups():
    """Percorsi dello stesso layer restano adiacenti."""
    a1 = FlatPath(points=[(0.0, 0.0), (1.0, 0.0)], closed=False,
                  entity_id="A1", layer_id="LA")
    a2 = FlatPath(points=[(1.0, 0.0), (2.0, 0.0)], closed=False,
                  entity_id="A2", layer_id="LA")
    b1 = FlatPath(points=[(100.0, 100.0), (101.0, 100.0)], closed=False,
                  entity_id="B1", layer_id="LB")

    ordered = order_paths([b1, a1, a2], start=(0.0, 0.0))
    layers = [p.layer_id for p in ordered]
    # I layer uguali devono formare un blocco contiguo (nessun mescolamento)
    assert layers in (["LB", "LA", "LA"], ["LA", "LA", "LB"])

def test_order_follows_input_layer_order():
    """Se i paths arrivano già ordinati per layer, l'ordine è preservato."""
    a1 = FlatPath(points=[(0.0, 0.0), (1.0, 0.0)], closed=False,
                  entity_id="A1", layer_id="LA")
    a2 = FlatPath(points=[(1.0, 0.0), (2.0, 0.0)], closed=False,
                  entity_id="A2", layer_id="LA")
    b1 = FlatPath(points=[(100.0, 100.0), (101.0, 100.0)], closed=False,
                  entity_id="B1", layer_id="LB")

    ordered = order_paths([a1, a2, b1], start=(0.0, 0.0))
    ids = [p.entity_id for p in ordered]
    assert ids == ["A1", "A2", "B1"]

def test_order_empty_returns_empty():
    assert order_paths([]) == []