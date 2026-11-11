"""Utility per convertire archi (cerchio/ellisse) in curve di Bézier cubiche.

Approssimazione ottimale (errore massimo ~0.027% del raggio) usando la
formula classica con ``h = 4/3 * tan(delta/4)``. Splitting in archi da ≤90°
garantisce che l'errore resti trascurabile.

Ogni ``BezierSegment`` è una cubica con 4 punti di controllo. Il chiamante
converte la lista in ``PathNode`` tramite ``append_bezier_segments_to_path``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from lasercontrolsuite.core.path import PathNode


_HALF_PI = math.pi / 2.0
_EPS = 1e-12


@dataclass(frozen=True)
class BezierSegment:
    """Cubica di Bézier con 4 punti di controllo assoluti."""

    p0: tuple[float, float]
    p1: tuple[float, float]
    p2: tuple[float, float]
    p3: tuple[float, float]


# =====================================================================
# Splitting
# =====================================================================
def _split_into_steps(start: float, end: float) -> list[tuple[float, float]]:
    """Divide ``[start, end]`` in sotto-intervalli di ampiezza ≤ π/2."""
    sweep = end - start
    if abs(sweep) < _EPS:
        return []
    n = max(1, int(math.ceil(abs(sweep) / _HALF_PI)))
    step = sweep / n
    return [(start + i * step, start + (i + 1) * step) for i in range(n)]


# =====================================================================
# Arco di cerchio
# =====================================================================
def arc_to_bezier_segments(
    cx: float, cy: float, r: float,
    start_angle: float, end_angle: float,
) -> list[BezierSegment]:
    """Converte un arco di cerchio (angoli in radianti) in Bézier cubiche.

    Il segno di ``end_angle - start_angle`` determina il verso (positivo = CCW).
    """
    segments: list[BezierSegment] = []
    for a0, a1 in _split_into_steps(start_angle, end_angle):
        delta = a1 - a0
        h = (4.0 / 3.0) * math.tan(delta / 4.0)

        p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
        p3 = (cx + r * math.cos(a1), cy + r * math.sin(a1))

        t0 = (-math.sin(a0), math.cos(a0))  # tangente CCW in a0
        t1 = (-math.sin(a1), math.cos(a1))  # tangente CCW in a1

        p1 = (p0[0] + h * r * t0[0], p0[1] + h * r * t0[1])
        p2 = (p3[0] - h * r * t1[0], p3[1] - h * r * t1[1])

        segments.append(BezierSegment(p0, p1, p2, p3))
    return segments


# =====================================================================
# Arco di ellisse
# =====================================================================
def elliptical_arc_to_bezier_segments(
    cx: float, cy: float,
    a: float, b: float,
    rotation: float,
    start_param: float, end_param: float,
) -> list[BezierSegment]:
    """Converte un arco di ellisse in Bézier cubiche.

    Args:
        cx, cy: centro.
        a: semiasse lungo la direzione ``rotation``.
        b: semiasse perpendicolare.
        rotation: rotazione in radianti dell'asse ``a`` rispetto all'asse X.
        start_param, end_param: angoli **parametrici** (radianti), non geometrici.

    Parametrizzazione:
        ``P(t) = C + a·cos(t)·u + b·sin(t)·v``
        con ``u = (cos φ, sin φ)``, ``v = (-sin φ, cos φ)``.
    """
    segments: list[BezierSegment] = []
    cos_phi = math.cos(rotation)
    sin_phi = math.sin(rotation)

    def _point(t: float) -> tuple[float, float]:
        return (
            cx + a * math.cos(t) * cos_phi - b * math.sin(t) * sin_phi,
            cy + a * math.cos(t) * sin_phi + b * math.sin(t) * cos_phi,
        )

    def _derivative(t: float) -> tuple[float, float]:
        return (
            -a * math.sin(t) * cos_phi - b * math.cos(t) * sin_phi,
            -a * math.sin(t) * sin_phi + b * math.cos(t) * cos_phi,
        )

    for t0, t1 in _split_into_steps(start_param, end_param):
        delta = t1 - t0
        h = (4.0 / 3.0) * math.tan(delta / 4.0)

        p0 = _point(t0)
        p3 = _point(t1)
        d0 = _derivative(t0)
        d1 = _derivative(t1)

        p1 = (p0[0] + h * d0[0], p0[1] + h * d0[1])
        p2 = (p3[0] - h * d1[0], p3[1] - h * d1[1])

        segments.append(BezierSegment(p0, p1, p2, p3))
    return segments


# =====================================================================
# Applicazione a una lista di PathNode
# =====================================================================
def append_bezier_segments_to_path(
    nodes: list[PathNode],
    segments: list[BezierSegment],
) -> None:
    """Converte ``segments`` in nodi e li appende a ``nodes``.

    Richiede che ``nodes`` abbia **almeno un nodo** (il punto iniziale).
    Per ogni segmento:
      - il nodo precedente riceve ``handle_out = p1 - p0``
      - viene aggiunto un nuovo nodo in ``p3`` con ``handle_in = p2 - p3``

    Il punto ``p0`` del primo segmento deve coincidere con l'ultimo nodo di
    ``nodes`` (verrà agganciato da ``handle_out``). Se non coincide, lo
    scostamento è ignorato (l'utente ha costruito il segmento staccato).
    """
    if not segments:
        return
    if not nodes:
        # Nessun nodo iniziale: creiamo il primo da p0 del primo segmento
        nodes.append(PathNode(point=segments[0].p0))

    for seg in segments:
        prev = nodes[-1]
        prev.handle_out = (
            seg.p1[0] - prev.point[0],
            seg.p1[1] - prev.point[1],
        )
        nodes.append(
            PathNode(
                point=seg.p3,
                handle_in=(seg.p2[0] - seg.p3[0], seg.p2[1] - seg.p3[1]),
            )
        )