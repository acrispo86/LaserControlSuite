"""Path editabile a nodi (linee e curve di Bézier cubiche).

Un ``PathEntity`` è una sequenza di ``PathNode`` collegati da segmenti, ognuno
dei quali è **linea** (se i due nodi non hanno handle) oppure **cubica di
Bézier** (se almeno uno dei due ha un handle).

Convenzioni:
  - Gli handle sono memorizzati in coordinate **relative al nodo**.
  - ``handle_in`` punta verso il nodo precedente, ``handle_out`` verso il
    successivo. Se entrambi sono ``None``, il nodo è un angolo.
  - Gli handle possono essere simmetrici (smooth) o indipendenti (corner).
  - Un path ``closed`` collega l'ultimo nodo al primo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from lasercontrolsuite.core.entities import Entity, PointTuple


#: Numero di campioni per ogni segmento curvo in ``local_points()``.
SAMPLES_PER_CURVE: int = 16


@dataclass
class PathNode:
    """Nodo di un path."""

    point: PointTuple
    handle_in: PointTuple | None = None
    handle_out: PointTuple | None = None

    def abs_handle_in(self) -> PointTuple | None:
        if self.handle_in is None:
            return None
        return (self.point[0] + self.handle_in[0], self.point[1] + self.handle_in[1])

    def abs_handle_out(self) -> PointTuple | None:
        if self.handle_out is None:
            return None
        return (self.point[0] + self.handle_out[0], self.point[1] + self.handle_out[1])

    def is_corner(self) -> bool:
        return self.handle_in is None and self.handle_out is None


def _sample_cubic(p0, p1, p2, p3, n: int) -> list[PointTuple]:
    out: list[PointTuple] = []
    for i in range(1, n + 1):  # skip p0, già aggiunto dal chiamante
        t = i / n
        mt = 1.0 - t
        b0 = mt * mt * mt
        b1 = 3.0 * mt * mt * t
        b2 = 3.0 * mt * t * t
        b3 = t * t * t
        out.append(
            (
                b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
                b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1],
            )
        )
    return out


@dataclass
class PathEntity(Entity):
    """Path a nodi, con segmenti linea e/o cubici."""

    nodes: list[PathNode] = field(default_factory=list)
    closed: bool = False

    # ------------------------------------------------------------- geometria
    def local_points(self) -> list[PointTuple]:
        nodes = self.nodes
        if not nodes:
            return []
        if len(nodes) == 1:
            return [nodes[0].point]

        pts: list[PointTuple] = [nodes[0].point]
        n = len(nodes)
        last = n if self.closed else n - 1
        for i in range(last):
            a = nodes[i]
            b = nodes[(i + 1) % n]
            if a.handle_out is None and b.handle_in is None:
                pts.append(b.point)
            else:
                p0 = a.point
                p1 = a.abs_handle_out() or p0
                p2 = b.abs_handle_in() or b.point
                p3 = b.point
                pts.extend(_sample_cubic(p0, p1, p2, p3, SAMPLES_PER_CURVE))
        return pts

    def local_snap_points(self) -> list[PointTuple]:
        """Snap ai nodi e agli handle (comodi per agganciarsi mentre si edita)."""
        pts: list[PointTuple] = []
        for node in self.nodes:
            pts.append(node.point)
            hi = node.abs_handle_in()
            ho = node.abs_handle_out()
            if hi is not None:
                pts.append(hi)
            if ho is not None:
                pts.append(ho)
        return pts

    # ------------------------------------------------------------- utility
    def segment_count(self) -> int:
        if len(self.nodes) < 2:
            return 0
        return len(self.nodes) if self.closed else len(self.nodes) - 1

    def is_closed_path(self) -> bool:
        return self.closed and len(self.nodes) >= 3

    def bounding_box_of_node(self, index: int) -> tuple[float, float, float, float]:
        """Piccolo AABB attorno a un nodo (usato dal node editor)."""
        r = 0.5
        p = self.nodes[index].point
        return (p[0] - r, p[1] - r, p[0] + r, p[1] + r)


# =====================================================================
# Conversione da PolylineEntity a PathEntity
# =====================================================================
def polyline_to_path(polyline) -> PathEntity:
    """Converte una ``PolylineEntity`` in un ``PathEntity`` a soli segmenti rettilinei.

    Utile nel node editor: un path con soli corner è editabile nodo per nodo.
    """
    nodes = [PathNode(point=(x, y)) for (x, y) in polyline.points]
    return PathEntity(
        layer_id=polyline.layer_id,
        nodes=nodes,
        closed=polyline.closed,
        transform=polyline.transform,
    )


def angle_of_handle(dx: float, dy: float) -> float:
    """Angolo in radianti dell'handle (utility per editing futuro)."""
    return math.atan2(dy, dx)