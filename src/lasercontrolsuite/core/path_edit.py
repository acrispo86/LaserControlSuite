"""Operazioni pure di editing di un PathEntity.

Le funzioni operano **in place** su ``PathEntity.nodes``; lo snapshot per
undo/redo è gestito a monte (nel comando Qt). Tutte le coordinate sono in
sistema **locale** del path.

Convenzioni di ritorno:
  - ``find_*`` ritornano ``None`` se non c'è match entro tolleranza.
  - Le tolleranze sono espresse in unità di scena (mm); il chiamante le
    converte da pixel dividendole per ``px_per_unit``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from lasercontrolsuite.core.entities import (
    BezierEntity,
    CircleEntity,
    EllipseEntity,
    Entity,
    PointTuple,
    PolygonEntity,
    PolylineEntity,
    StarEntity,
)
from lasercontrolsuite.core.path import PathEntity, PathNode, _sample_cubic


# =====================================================================
# Tipi di ritorno per gli hit test
# =====================================================================
class HandleKind(str, Enum):
    IN = "in"
    OUT = "out"


@dataclass(frozen=True)
class NodeHit:
    index: int
    distance: float


@dataclass(frozen=True)
class HandleHit:
    node_index: int
    kind: HandleKind
    distance: float


@dataclass(frozen=True)
class SegmentHit:
    segment_index: int
    t: float
    distance: float
    point: PointTuple


# =====================================================================
# Hit test
# =====================================================================
def find_nearest_node(
    path: PathEntity, target: PointTuple, tolerance: float
) -> NodeHit | None:
    best: NodeHit | None = None
    for i, node in enumerate(path.nodes):
        d = math.hypot(node.point[0] - target[0], node.point[1] - target[1])
        if d <= tolerance and (best is None or d < best.distance):
            best = NodeHit(index=i, distance=d)
    return best


def find_nearest_handle(
    path: PathEntity, target: PointTuple, tolerance: float
) -> HandleHit | None:
    best: HandleHit | None = None
    for i, node in enumerate(path.nodes):
        for kind in (HandleKind.IN, HandleKind.OUT):
            abs_h = node.abs_handle_in() if kind is HandleKind.IN else node.abs_handle_out()
            if abs_h is None:
                continue
            d = math.hypot(abs_h[0] - target[0], abs_h[1] - target[1])
            if d <= tolerance and (best is None or d < best.distance):
                best = HandleHit(node_index=i, kind=kind, distance=d)
    return best


def find_nearest_segment(
    path: PathEntity, target: PointTuple, tolerance: float
) -> SegmentHit | None:
    n = len(path.nodes)
    if n < 2:
        return None
    num_segments = n if path.closed else n - 1
    best: SegmentHit | None = None

    for seg in range(num_segments):
        a = path.nodes[seg]
        b = path.nodes[(seg + 1) % n]
        if a.handle_out is None and b.handle_in is None:
            hit = _project_on_line(a.point, b.point, target)
        else:
            hit = _project_on_cubic(a, b, target)
        if hit is None:
            continue
        t, point, dist = hit
        if dist <= tolerance and (best is None or dist < best.distance):
            best = SegmentHit(segment_index=seg, t=t, distance=dist, point=point)
    return best


def _project_on_line(
    p0: PointTuple, p1: PointTuple, target: PointTuple
) -> tuple[float, PointTuple, float] | None:
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-20:
        return None
    t = ((target[0] - p0[0]) * dx + (target[1] - p0[1]) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    point = (p0[0] + t * dx, p0[1] + t * dy)
    d = math.hypot(target[0] - point[0], target[1] - point[1])
    return t, point, d


def _project_on_cubic(
    a: PathNode, b: PathNode, target: PointTuple, samples: int = 24
) -> tuple[float, PointTuple, float] | None:
    p0 = a.point
    p1 = a.abs_handle_out() or p0
    p2 = b.abs_handle_in() or b.point
    p3 = b.point
    pts = _sample_cubic(p0, p1, p2, p3, samples)
    full = [p0] + pts

    best: tuple[float, PointTuple, float] | None = None
    for i, p in enumerate(full):
        d = math.hypot(target[0] - p[0], target[1] - p[1])
        if best is None or d < best[2]:
            t = i / (len(full) - 1)
            best = (t, p, d)
    return best


# =====================================================================
# Modifiche strutturali
# =====================================================================
def add_node_at_segment(path: PathEntity, segment_index: int, t: float) -> int:
    t = max(0.0, min(1.0, t))
    n = len(path.nodes)
    if n < 2:
        raise ValueError("Servono almeno due nodi per inserire un nodo")
    num_segments = n if path.closed else n - 1
    if not (0 <= segment_index < num_segments):
        raise IndexError(f"segment_index {segment_index} fuori range [0, {num_segments})")

    ia = segment_index
    ib = (segment_index + 1) % n
    a = path.nodes[ia]
    b = path.nodes[ib]

    is_line = a.handle_out is None and b.handle_in is None
    if is_line:
        pt = (a.point[0] + t * (b.point[0] - a.point[0]),
              a.point[1] + t * (b.point[1] - a.point[1]))
        new_node = PathNode(point=pt)
        insert_at = ia + 1
        path.nodes.insert(insert_at, new_node)
        return insert_at

    p0 = a.point
    p1 = a.abs_handle_out() or p0
    p2 = b.abs_handle_in() or b.point
    p3 = b.point

    q1 = _lerp(p0, p1, t)
    m12 = _lerp(p1, p2, t)
    q2 = _lerp(q1, m12, t)
    m23 = _lerp(p2, p3, t)
    r1 = _lerp(m12, m23, t)
    r2 = _lerp(p2, p3, t)
    q3 = _lerp(q2, r1, t)

    a.handle_out = (q1[0] - p0[0], q1[1] - p0[1])
    b.handle_in = (r2[0] - p3[0], r2[1] - p3[1])
    new_node = PathNode(
        point=q3,
        handle_in=(q2[0] - q3[0], q2[1] - q3[1]),
        handle_out=(r1[0] - q3[0], r1[1] - q3[1]),
    )
    insert_at = ia + 1
    path.nodes.insert(insert_at, new_node)
    return insert_at


def remove_node_at(path: PathEntity, index: int) -> None:
    if not (0 <= index < len(path.nodes)):
        raise IndexError(f"index {index} fuori range")
    if len(path.nodes) <= 2:
        return
    path.nodes.pop(index)


def set_node_corner(path: PathEntity, index: int) -> None:
    node = path.nodes[index]
    node.handle_in = None
    node.handle_out = None


def set_node_smooth(path: PathEntity, index: int, tangent_length: float | None = None) -> None:
    n = len(path.nodes)
    if n < 2:
        return
    node = path.nodes[index]

    if node.handle_out is not None:
        tx, ty = node.handle_out
    elif node.handle_in is not None:
        tx, ty = -node.handle_in[0], -node.handle_in[1]
    else:
        prev_i = (index - 1) % n
        next_i = (index + 1) % n
        prev_p = path.nodes[prev_i].point
        next_p = path.nodes[next_i].point
        tx = next_p[0] - prev_p[0]
        ty = next_p[1] - prev_p[1]

    length = math.hypot(tx, ty)
    if length < 1e-9:
        return
    if tangent_length is None:
        prev_i = (index - 1) % n
        next_i = (index + 1) % n
        d_prev = math.hypot(node.point[0] - path.nodes[prev_i].point[0],
                            node.point[1] - path.nodes[prev_i].point[1])
        d_next = math.hypot(node.point[0] - path.nodes[next_i].point[0],
                            node.point[1] - path.nodes[next_i].point[1])
        tangent_length = max(1.0, (d_prev + d_next) / 6.0)

    ux, uy = tx / length, ty / length
    node.handle_out = (ux * tangent_length, uy * tangent_length)
    node.handle_in = (-ux * tangent_length, -uy * tangent_length)


def move_node(path: PathEntity, index: int, dx: float, dy: float) -> None:
    node = path.nodes[index]
    node.point = (node.point[0] + dx, node.point[1] + dy)


def move_handle(
    path: PathEntity,
    node_index: int,
    kind: HandleKind,
    new_abs_pos: PointTuple,
    symmetric: bool = True,
) -> None:
    node = path.nodes[node_index]
    rel = (new_abs_pos[0] - node.point[0], new_abs_pos[1] - node.point[1])
    if kind is HandleKind.OUT:
        node.handle_out = rel
        if symmetric and node.handle_in is not None:
            node.handle_in = (-rel[0], -rel[1])
    else:
        node.handle_in = rel
        if symmetric and node.handle_out is not None:
            node.handle_out = (-rel[0], -rel[1])


def is_smooth_node(node: PathNode, tol: float = 1e-6) -> bool:
    if node.handle_in is None or node.handle_out is None:
        return False
    return (
        abs(node.handle_in[0] + node.handle_out[0]) < tol
        and abs(node.handle_in[1] + node.handle_out[1]) < tol
    )


# =====================================================================
# Curvatura diretta di un segmento (drag su segmento)
# =====================================================================
def curve_line_segment_through_point(
    path: PathEntity,
    segment_index: int,
    target: PointTuple,
    min_projection: float = 1e-3,
) -> bool:
    """Trasforma un segmento **rettilineo** in una cubica passante per ``target``.

    Il punto medio della cubica risultante coincide con la proiezione di
    ``target`` sulla normale del segmento. Semantica di Illustrator/Inkscape:
    trascinando un segmento lateralmente, la curva si piega in modo simmetrico.

    Ritorna False se il segmento non è rettilineo o la proiezione è degenere.
    """
    n = len(path.nodes)
    if n < 2:
        return False
    num_segments = n if path.closed else n - 1
    if not (0 <= segment_index < num_segments):
        return False

    a = path.nodes[segment_index]
    b = path.nodes[(segment_index + 1) % n]

    if a.handle_out is not None or b.handle_in is not None:
        return False

    dx = b.point[0] - a.point[0]
    dy = b.point[1] - a.point[1]
    seg_len = math.hypot(dx, dy)
    if seg_len < 1e-9:
        return False

    nx = -dy / seg_len
    ny = dx / seg_len

    mid_x = (a.point[0] + b.point[0]) / 2.0
    mid_y = (a.point[1] + b.point[1]) / 2.0

    proj = (target[0] - mid_x) * nx + (target[1] - mid_y) * ny
    if abs(proj) < min_projection:
        return False

    h = (4.0 / 3.0) * proj

    a.handle_out = (dx / 3.0 + h * nx, dy / 3.0 + h * ny)
    b.handle_in = (-dx / 3.0 + h * nx, -dy / 3.0 + h * ny)
    return True


def translate_curve_segment(
    path: PathEntity, segment_index: int, dx: float, dy: float
) -> bool:
    """Trasla rigidamente i due handle del segmento di ``(dx, dy)``."""
    n = len(path.nodes)
    if n < 2:
        return False
    num_segments = n if path.closed else n - 1
    if not (0 <= segment_index < num_segments):
        return False

    a = path.nodes[segment_index]
    b = path.nodes[(segment_index + 1) % n]

    if a.handle_out is None and b.handle_in is None:
        return False

    if a.handle_out is not None:
        a.handle_out = (a.handle_out[0] + dx, a.handle_out[1] + dy)
    if b.handle_in is not None:
        b.handle_in = (b.handle_in[0] + dx, b.handle_in[1] + dy)
    return True


# =====================================================================
# Conversione entità → PathEntity
# =====================================================================
def entity_to_path(entity: Entity) -> PathEntity | None:
    """Converte un'entità in un ``PathEntity`` equivalente.

    Regole:
      - ``PathEntity`` → ritornata così com'è (già convertita).
      - ``PolylineEntity`` → nodi corner sui punti, ``closed`` preservato.
      - ``CircleEntity`` / ``EllipseEntity`` → nodi corner sui punti campionati
        (64/96 segmenti), ``closed=True``. Nota: in futuro implementeremo la
        conversione esatta a 4 archi di Bézier.
      - ``PolygonEntity`` / ``StarEntity`` → nodi corner sui vertici,
        ``closed=True``.
      - ``BezierEntity`` → due nodi (P0 e P3) con handle derivati da P1 e P2.
      - Altri tipi (``TextEntity``) → ``None`` (non convertibili).

    L'id, il layer, la transform e i flag di visibilità/lock vengono
    preservati.
    """
    if isinstance(entity, PathEntity):
        return entity

    if isinstance(entity, PolylineEntity):
        nodes = [PathNode((x, y)) for (x, y) in entity.points]
        closed = entity.closed
    elif isinstance(entity, (CircleEntity, EllipseEntity, PolygonEntity, StarEntity)):
        nodes = [PathNode((x, y)) for (x, y) in entity.local_points()]
        closed = True
    elif isinstance(entity, BezierEntity):
        p0 = entity.p0
        p1 = entity.p1
        p2 = entity.p2
        p3 = entity.p3
        nodes = [
            PathNode(
                point=p0,
                handle_out=(p1[0] - p0[0], p1[1] - p0[1]),
            ),
            PathNode(
                point=p3,
                handle_in=(p2[0] - p3[0], p2[1] - p3[1]),
            ),
        ]
        closed = False
    else:
        return None

    if not nodes:
        return None

    return PathEntity(
        id=entity.id,
        layer_id=entity.layer_id,
        transform=entity.transform,
        visible=entity.visible,
        locked=entity.locked,
        nodes=nodes,
        closed=closed,
    )


# =====================================================================
# Helpers
# =====================================================================
def _lerp(a: PointTuple, b: PointTuple, t: float) -> PointTuple:
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))