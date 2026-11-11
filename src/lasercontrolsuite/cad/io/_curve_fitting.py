"""Fit di curve da nuvola di punti (per archi esplosi in polilinee).

Include:
  1. ``fit_circle_arc``: fit circolare rapido (3 punti). Perfetto per cerchi/archi.
  2. ``fit_bezier_curve``: fit di curve di Bézier generico (Schneider).
     Protetto da ``is_smooth_for_bezier_fit``: rifiuta polilinee a zig-zag.
"""

from __future__ import annotations

import math
import numpy as np


_COLLINEAR_EPS: float = 1e-9


# =====================================================================
# Check di liscezza
# =====================================================================
def is_smooth_for_bezier_fit(
    pts: list[tuple[float, float]],
    max_turn_deg: float = 60.0,
    max_turn_ratio: float = 0.2,
) -> bool:
    """Verifica se una polilinea è "abbastanza liscia" per essere una curva.

    Una polilinea che alterna bruscamente direzione (zig-zag, dente di sega)
    non è una curva esplosa: è geometria intenzionale. Questo check misura
    l'angolo tra segmenti consecutivi e rifiuta la polilinea se:
      - più del ``max_turn_ratio`` dei vertici ha una svolta > ``max_turn_deg``
      - oppure una singola svolta supera 150° (inversione quasi totale)

    Args:
        pts: lista di punti ``(x, y)`` in mm.
        max_turn_deg: soglia di svolta considerata "brusca".
        max_turn_ratio: frazione massima di vertici con svolta brusca.

    Returns:
        True se la polilinea è liscia (fit Bézier tentabile), False altrimenti.
    """
    if len(pts) < 3:
        return False

    turns: list[float] = []
    for i in range(1, len(pts) - 1):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        v1x, v1y = x1 - x0, y1 - y0
        v2x, v2y = x2 - x1, y2 - y1
        n1 = math.hypot(v1x, v1y)
        n2 = math.hypot(v2x, v2y)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        dot = (v1x * v2x + v1y * v2y) / (n1 * n2)
        dot = max(-1.0, min(1.0, dot))
        turns.append(math.degrees(math.acos(dot)))

    if not turns:
        return False

    if max(turns) > 150.0:
        return False

    n_bruschi = sum(1 for t in turns if t > max_turn_deg)
    if n_bruschi / len(turns) > max_turn_ratio:
        return False

    return True


# =====================================================================
# Fit circolare (3 punti)
# =====================================================================
def fit_circle_arc(
    pts: list[tuple[float, float]],
    tolerance_mm: float = 0.2,
) -> tuple[float, float, float, float, float, bool] | None:
    """Fitta un arco circolare ai punti dati."""
    if len(pts) < 3:
        return None

    p0 = pts[0]
    pm = pts[len(pts) // 2]
    pn = pts[-1]

    circle = _circle_through_3_points(p0, pm, pn)
    if circle is None:
        return None
    cx, cy, r = circle
    if r < 1e-9:
        return None

    max_err = 0.0
    for x, y in pts:
        err = abs(math.hypot(x - cx, y - cy) - r)
        if err > max_err:
            max_err = err
    if max_err > tolerance_mm:
        return None

    angles = [math.atan2(y - cy, x - cx) for x, y in pts]

    total_sweep = 0.0
    for i in range(1, len(angles)):
        d = angles[i] - angles[i - 1]
        while d > math.pi:
            d -= 2.0 * math.pi
        while d < -math.pi:
            d += 2.0 * math.pi
        total_sweep += d

    closed = math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 0.01
    if closed:
        total_sweep = 2.0 * math.pi if total_sweep >= 0.0 else -2.0 * math.pi

    a0 = angles[0]
    a1 = a0 + total_sweep
    return cx, cy, r, a0, a1, closed


def _circle_through_3_points(p0, pm, pn) -> tuple[float, float, float] | None:
    ax, ay = p0
    bx, by = pm
    cx_pt, cy_pt = pn

    d = 2.0 * (ax * (by - cy_pt) + bx * (cy_pt - ay) + cx_pt * (ay - by))
    if abs(d) < _COLLINEAR_EPS:
        return None

    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx_pt * cx_pt + cy_pt * cy_pt

    ux = (a2 * (by - cy_pt) + b2 * (cy_pt - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx_pt - bx) + b2 * (ax - cx_pt) + c2 * (bx - ax)) / d

    r = math.hypot(ax - ux, ay - uy)
    return ux, uy, r


# =====================================================================
# Fit di Bézier (Algoritmo di Schneider)
# =====================================================================
def fit_bezier_curve(
    points: list[tuple[float, float]],
    tolerance_mm: float = 0.2,
) -> list[tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]]:
    """Approssima una polilinea con curve di Bézier cubiche (Schneider)."""
    if len(points) < 2:
        return []
        
    pts = np.array([complex(x, y) for x, y in points])
    out = []
    
    t1 = _compute_tangent(pts, 0)
    t2 = _compute_tangent(pts, -1)
    
    _fit_recursive(pts, t1, t2, tolerance_mm, 0, 20, out)
    
    return [
        ((p[0].real, p[0].imag), (p[1].real, p[1].imag), 
         (p[2].real, p[2].imag), (p[3].real, p[3].imag))
        for p in out
    ]


def _compute_tangent(pts, idx):
    if idx == 0:
        return pts[1] - pts[0]
    elif idx == -1 or idx == len(pts) - 1:
        return pts[-1] - pts[-2]
    else:
        return pts[idx+1] - pts[idx-1]


def _fit_recursive(pts, t1, t2, tolerance, depth, max_depth, out):
    if len(pts) == 2:
        out.append((pts[0], pts[0] + t1/3, pts[-1] - t2/3, pts[-1]))
        return
        
    n = len(pts) - 1
    u = np.linspace(0, 1, len(pts))
    b0 = (1-u)**3
    b1 = 3*u*(1-u)**2
    b2 = 3*u**2*(1-u)
    b3 = u**3
    
    p0 = pts[0]
    p3 = pts[-1]
    
    A1 = t1 * b1
    A2 = -t2 * b2
    
    tmp = pts - (p0 * (b0 + b1) + p3 * (b2 + b3))
    
    A = np.column_stack((A1, A2))
    
    alpha = np.array([0.0, 0.0])
    try:
        alpha, _, _, _ = np.linalg.lstsq(A, tmp, rcond=None)
    except np.linalg.LinAlgError:
        pass
        
    alpha1 = max(alpha[0], 1e-6)
    alpha2 = max(alpha[1], 1e-6)
    
    p1 = p0 + t1 * alpha1
    p2 = p3 - t2 * alpha2
    
    bezier = p0 * b0 + p1 * b1 + p2 * b2 + p3 * b3
    error = np.abs(bezier - pts)
    max_err_idx = np.argmax(error)
    max_err = error[max_err_idx]
    
    if max_err < tolerance or depth >= max_depth:
        out.append((p0, p1, p2, p3))
    else:
        t_split = _compute_tangent(pts, max_err_idx)
        _fit_recursive(pts[:max_err_idx+1], t1, t_split, tolerance, depth+1, max_depth, out)
        _fit_recursive(pts[max_err_idx:], t_split, t2, tolerance, depth+1, max_depth, out)