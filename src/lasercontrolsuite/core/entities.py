"""Entità geometriche del documento (indipendenti da Qt).

Convenzioni (importanti per il CAM e per i tool):
  - Le entità **a punti locali assoluti** (``PolylineEntity``, ``BezierEntity``)
    hanno i punti direttamente in coordinate locali.
  - Le entità **parametriche** (``CircleEntity``, ``EllipseEntity``) hanno un
    centro ``(cx, cy)`` e raggi/assi nel sistema locale.
  - Le entità **a simmetria radiale** (``PolygonEntity``, ``StarEntity``) hanno
    la geometria locale **sempre centrata su (0, 0)**. La posizione nel mondo
    si esprime tramite la ``transform`` (es. ``translation(cx, cy) @ rotation(a)``).
  - ``TextEntity`` è ancorata all'origine locale; la posizione è nella transform.

Bounding box:
  ``local_bounding_box()`` è l'AABB della polilinea ``local_points()``.
  ``world_bounding_box()`` è l'AABB stretto della geometria trasformata.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from lasercontrolsuite.core.ids import new_id
from lasercontrolsuite.core.matrix import Matrix2D


PointTuple = tuple[float, float]


@dataclass
class Entity(ABC):
    """Entità astratta del documento."""

    id: str = field(default_factory=new_id)
    layer_id: str = ""
    transform: Matrix2D = field(default_factory=Matrix2D)
    visible: bool = True
    locked: bool = False

    # ------------------------------------------------------------- geometria locale
    @abstractmethod
    def local_points(self) -> list[PointTuple]:
        """Punti rappresentativi in coordinate locali (fonte di verità)."""

    def local_snap_points(self) -> list[PointTuple]:
        return self.local_points()

    def local_bounding_box(self) -> tuple[float, float, float, float]:
        pts = self.local_points()
        if not pts:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    # ------------------------------------------------------------- geometria mondo
    def world_points(self) -> list[PointTuple]:
        return self.transform.transform_points(self.local_points())

    def world_snap_points(self) -> list[PointTuple]:
        return self.transform.transform_points(self.local_snap_points())

    def world_bounding_box(self) -> tuple[float, float, float, float]:
        pts = self.world_points()
        if not pts:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    # ------------------------------------------------------------- display
    @property
    def type_name(self) -> str:
        return type(self).__name__


# =====================================================================
# Polilinea
# =====================================================================
@dataclass
class PolylineEntity(Entity):
    """Polilinea: copre linee, polilinee aperte e poligoni chiusi."""

    points: list[PointTuple] = field(default_factory=list)
    closed: bool = False

    @classmethod
    def line(
        cls, layer_id: str, x1: float, y1: float, x2: float, y2: float
    ) -> "PolylineEntity":
        return cls(layer_id=layer_id, points=[(x1, y1), (x2, y2)], closed=False)

    @classmethod
    def rect(
        cls, layer_id: str, x: float, y: float, w: float, h: float
    ) -> "PolylineEntity":
        return cls(
            layer_id=layer_id,
            points=[(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
            closed=True,
        )

    def local_points(self) -> list[PointTuple]:
        return list(self.points)

    def local_snap_points(self) -> list[PointTuple]:
        pts = list(self.points)
        if not pts:
            return []
        result = list(pts)
        n = len(pts)
        last = n if self.closed else n - 1
        for i in range(last):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            result.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
        return result


# =====================================================================
# Cerchio
# =====================================================================
@dataclass
class CircleEntity(Entity):
    cx: float = 0.0
    cy: float = 0.0
    r: float = 1.0

    _ARC_SEGMENTS: int = 64

    def local_points(self) -> list[PointTuple]:
        n = self._ARC_SEGMENTS
        return [
            (
                self.cx + self.r * math.cos(2.0 * math.pi * i / n),
                self.cy + self.r * math.sin(2.0 * math.pi * i / n),
            )
            for i in range(n)
        ]

    def local_snap_points(self) -> list[PointTuple]:
        return [
            (self.cx, self.cy),
            (self.cx + self.r, self.cy),
            (self.cx - self.r, self.cy),
            (self.cx, self.cy + self.r),
            (self.cx, self.cy - self.r),
        ]

    def local_bounding_box(self) -> tuple[float, float, float, float]:
        return (self.cx - self.r, self.cy - self.r, self.cx + self.r, self.cy + self.r)


# =====================================================================
# Ellisse
# =====================================================================
@dataclass
class EllipseEntity(Entity):
    cx: float = 0.0
    cy: float = 0.0
    rx: float = 1.0
    ry: float = 1.0

    _ARC_SEGMENTS: int = 96

    def local_points(self) -> list[PointTuple]:
        n = self._ARC_SEGMENTS
        return [
            (
                self.cx + self.rx * math.cos(2.0 * math.pi * i / n),
                self.cy + self.ry * math.sin(2.0 * math.pi * i / n),
            )
            for i in range(n)
        ]

    def local_snap_points(self) -> list[PointTuple]:
        return [
            (self.cx, self.cy),
            (self.cx + self.rx, self.cy),
            (self.cx - self.rx, self.cy),
            (self.cx, self.cy + self.ry),
            (self.cx, self.cy - self.ry),
        ]

    def local_bounding_box(self) -> tuple[float, float, float, float]:
        return (
            self.cx - self.rx,
            self.cy - self.ry,
            self.cx + self.rx,
            self.cy + self.ry,
        )


# =====================================================================
# Poligono regolare
# =====================================================================
@dataclass
class PolygonEntity(Entity):
    """Poligono regolare inscritto in un cerchio di raggio ``radius``.

    La geometria locale è **sempre centrata su (0, 0)**. La posizione e la
    rotazione nel mondo si esprimono tramite la ``transform``:
        ``transform = translation(cx, cy) @ rotation(angle)``.

    Il primo vertice è in alto (ore 12) nel sistema locale, coerente con
    LightBurn, Illustrator e AutoCAD POLYGON. Con ``sides=4`` si ottiene un
    rombo (quadrato ruotato di 45°); per un quadrato a lati H/V, applicare
    una rotazione di 45° alla transform.
    """

    radius: float = 1.0
    sides: int = 6

    def __post_init__(self) -> None:
        self.sides = max(3, int(self.sides))

    def local_points(self) -> list[PointTuple]:
        n = self.sides
        start = math.pi / 2.0
        return [
            (
                self.radius * math.cos(start + 2.0 * math.pi * i / n),
                self.radius * math.sin(start + 2.0 * math.pi * i / n),
            )
            for i in range(n)
        ]

    def local_snap_points(self) -> list[PointTuple]:
        pts = self.local_points()
        result = [(0.0, 0.0)] + pts
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            result.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0))
        return result


# =====================================================================
# Stella
# =====================================================================
@dataclass
class StarEntity(Entity):
    """Stella a ``points`` punte.

    La geometria locale è **sempre centrata su (0, 0)**. Posizione e
    rotazione si esprimono tramite la ``transform``.
    """

    outer_radius: float = 1.0
    inner_radius: float = 0.4
    points: int = 5

    def __post_init__(self) -> None:
        self.points = max(3, int(self.points))
        if self.inner_radius <= 0.0:
            self.inner_radius = self.outer_radius * 0.4
        if self.inner_radius >= self.outer_radius:
            self.inner_radius = self.outer_radius * 0.4

    def local_points(self) -> list[PointTuple]:
        n = self.points
        start = math.pi / 2.0
        result: list[PointTuple] = []
        for i in range(2 * n):
            angle = start + math.pi * i / n
            r = self.outer_radius if i % 2 == 0 else self.inner_radius
            result.append((r * math.cos(angle), r * math.sin(angle)))
        return result

    def local_snap_points(self) -> list[PointTuple]:
        return [(0.0, 0.0)] + self.local_points()


# =====================================================================
# Bézier cubica
# =====================================================================
@dataclass
class BezierEntity(Entity):
    """Curva di Bézier cubica con 4 punti di controllo.

    La curva è approssimata con ``_SAMPLES`` segmenti. Questa polilinea è la
    geometria di riferimento per bbox, snap e percorso CAM: un solo
    campionamento, una sola verità.
    """

    p0: PointTuple = (0.0, 0.0)
    p1: PointTuple = (0.0, 0.0)
    p2: PointTuple = (0.0, 0.0)
    p3: PointTuple = (0.0, 0.0)

    _SAMPLES: int = 48

    def _sample(self, n: int | None = None) -> list[PointTuple]:
        n = self._SAMPLES if n is None else max(2, int(n))
        pts: list[PointTuple] = []
        for i in range(n + 1):
            t = i / n
            mt = 1.0 - t
            b0 = mt * mt * mt
            b1 = 3.0 * mt * mt * t
            b2 = 3.0 * mt * t * t
            b3 = t * t * t
            x = (
                b0 * self.p0[0]
                + b1 * self.p1[0]
                + b2 * self.p2[0]
                + b3 * self.p3[0]
            )
            y = (
                b0 * self.p0[1]
                + b1 * self.p1[1]
                + b2 * self.p2[1]
                + b3 * self.p3[1]
            )
            pts.append((x, y))
        return pts

    def local_points(self) -> list[PointTuple]:
        return self._sample()

    def local_snap_points(self) -> list[PointTuple]:
        return [self.p0, self.p1, self.p2, self.p3]


# =====================================================================
# Testo
# =====================================================================
@dataclass
class TextEntity(Entity):
    """Testo ancorato all'origine locale (baseline sinistra).

    La posizione nel mondo è nella ``transform``.
    """

    text: str = ""
    font_family: str = "Arial"
    font_size_mm: float = 10.0

    def _approx_size(self) -> tuple[float, float]:
        w = max(1.0, len(self.text) * self.font_size_mm * 0.6)
        h = self.font_size_mm
        return (w, h)

    def local_points(self) -> list[PointTuple]:
        w, h = self._approx_size()
        return [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]

    def local_snap_points(self) -> list[PointTuple]:
        w, h = self._approx_size()
        return [
            (0.0, 0.0),
            (w, 0.0),
            (w, h),
            (0.0, h),
            (w / 2.0, h / 2.0),
            (w / 2.0, 0.0),
        ]