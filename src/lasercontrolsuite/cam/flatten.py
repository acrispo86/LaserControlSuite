"""Appiattimento delle entità del core in polilinee mondo (mm).

Step 9c — ``FlatPath`` porta anche ``layer_id`` per permettere al motore CAM
di raggruppare i percorsi per layer (necessario per parametri per-layer).

Contratto sulla visibilità (invariato):
  - ``flatten_entity(entity, include_hidden=False)``: filtra le entità
    invisibili per default.
  - ``flatten_document(document, include_hidden=False)``: stesso filtro a
    livello documento; delega a ``flatten_entity`` (una sola fonte di
    verità per la visibilità).
"""

from __future__ import annotations

from dataclasses import dataclass

from lasercontrolsuite.core.entities import (
    BezierEntity,
    CircleEntity,
    EllipseEntity,
    Entity,
    PolygonEntity,
    PolylineEntity,
    StarEntity,
    TextEntity,
)
from lasercontrolsuite.core.path import PathEntity


@dataclass(frozen=True)
class FlatPath:
    """Polilinea appiattita in coordinate mondo (mm)."""

    points: list[tuple[float, float]]
    closed: bool
    entity_id: str
    layer_id: str = ""


def flatten_entity(
    entity: Entity, include_hidden: bool = False
) -> list[FlatPath]:
    """Appiattisce una entità in una o più ``FlatPath``."""
    if not include_hidden and not entity.visible:
        return []

    if isinstance(entity, PathEntity):
        return _flatten_path(entity)
    if isinstance(entity, PolylineEntity):
        return _flatten_polyline(entity)
    if isinstance(entity, CircleEntity):
        return _flatten_circle(entity)
    if isinstance(entity, EllipseEntity):
        return _flatten_ellipse(entity)
    if isinstance(entity, (PolygonEntity, StarEntity)):
        return _flatten_polygon_or_star(entity)
    if isinstance(entity, BezierEntity):
        return _flatten_bezier(entity)
    if isinstance(entity, TextEntity):
        # TODO (Step 9+): conversione testo → path vettoriale.
        return []
    return []


def flatten_document(
    document, *, include_hidden: bool = False
) -> list[FlatPath]:
    """Appiattisce tutte le entità del documento (una sola fonte di verità)."""
    out: list[FlatPath] = []
    for entity in document.entities.values():
        out.extend(flatten_entity(entity, include_hidden=include_hidden))
    return out


# =====================================================================
# Helpers per tipo
# =====================================================================
def _world_points(
    entity: Entity, local_points: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    return entity.transform.transform_points(local_points)


def _make_path(
    entity: Entity,
    world_points: list[tuple[float, float]],
    closed: bool,
) -> list[FlatPath]:
    return [
        FlatPath(
            points=world_points,
            closed=closed,
            entity_id=entity.id,
            layer_id=entity.layer_id,
        )
    ]


def _flatten_path(entity: PathEntity) -> list[FlatPath]:
    if len(entity.nodes) < 2:
        return []
    pts = entity.local_points()
    world = _world_points(entity, pts)
    return _make_path(entity, world, closed=entity.closed)


def _flatten_polyline(entity: PolylineEntity) -> list[FlatPath]:
    if len(entity.points) < 2:
        return []
    world = _world_points(entity, entity.points)
    return _make_path(entity, world, closed=entity.closed)


def _flatten_circle(entity: CircleEntity) -> list[FlatPath]:
    pts = _world_points(entity, entity.local_points())
    return _make_path(entity, pts, closed=True)


def _flatten_ellipse(entity: EllipseEntity) -> list[FlatPath]:
    pts = _world_points(entity, entity.local_points())
    return _make_path(entity, pts, closed=True)


def _flatten_polygon_or_star(entity) -> list[FlatPath]:
    pts = _world_points(entity, entity.local_points())
    if len(pts) < 2:
        return []
    return _make_path(entity, pts, closed=True)


def _flatten_bezier(entity: BezierEntity) -> list[FlatPath]:
    pts = _world_points(entity, entity.local_points())
    if len(pts) < 2:
        return []
    return _make_path(entity, pts, closed=False)