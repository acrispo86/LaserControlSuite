"""Importatore DXF → entità del core."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

from lasercontrolsuite.cad.io._bezier_utils import (
    append_bezier_segments_to_path,
    arc_to_bezier_segments,
    elliptical_arc_to_bezier_segments,
)
from lasercontrolsuite.cad.io._curve_fitting import (
    fit_bezier_curve,
    fit_circle_arc,
    is_smooth_for_bezier_fit,
)
from lasercontrolsuite.cad.io.units import dxf_unit_scale_mm
from lasercontrolsuite.core.entities import (
    CircleEntity,
    Entity,
    PolylineEntity,
)
from lasercontrolsuite.core.path import PathEntity, PathNode


GEOM_TOLERANCE_MM: float = 0.05
SPLINE_MAX_SEGMENTS: int = 20
POLYLINE_ARC_FIT_THRESHOLD: int = 20
ARC_FIT_TOLERANCE_MM: float = 0.2


@dataclass
class DxfImportResult:
    entities: list[Entity] = field(default_factory=list)
    layer_id: str = ""
    source_path: str = ""
    unit_scale: float = 1.0
    warnings: list[str] = field(default_factory=list)

    def bounds(self) -> tuple[float, float, float, float]:
        if not self.entities:
            return (0.0, 0.0, 0.0, 0.0)
        boxes = [e.world_bounding_box() for e in self.entities]
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        return (x0, y0, x1, y1)


def import_dxf(path: str | Path, layer_id: str) -> DxfImportResult:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File DXF non trovato: {path}")

    doc = ezdxf.readfile(str(p))
    insunits = int(doc.header.get("$INSUNITS", 4) or 4)
    unit_scale = dxf_unit_scale_mm(insunits)

    result = DxfImportResult(
        layer_id=layer_id, source_path=str(p), unit_scale=unit_scale
    )

    for entity in doc.modelspace():
        try:
            converted = _convert_entity(entity, unit_scale, layer_id, result.warnings)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"{entity.dxftype()}: {exc}")
            continue
        result.entities.extend(converted)

    return result


# =====================================================================
# Dispatch
# =====================================================================
def _convert_entity(e, scale, layer_id, warnings) -> list[Entity]:
    handler = _HANDLERS.get(e.dxftype())
    if handler is None:
        warnings.append(f"Tipo non supportato: {e.dxftype()}")
        return []
    return handler(e, scale, layer_id, warnings)


def _convert_line(e, scale, layer_id, warnings) -> list[Entity]:
    s, en = e.dxf.start, e.dxf.end
    return [PolylineEntity.line(
        layer_id=layer_id,
        x1=s.x * scale, y1=s.y * scale,
        x2=en.x * scale, y2=en.y * scale,
    )]


# =====================================================================
# LWPOLYLINE
# =====================================================================
def _convert_lwpolyline(e, scale, layer_id, warnings) -> list[Entity]:
    raw_points = list(e.get_points("xyb"))
    if len(raw_points) < 2:
        return []
    path = _build_bulge_path(raw_points, bool(e.closed), scale, layer_id)
    return [path] if path is not None else []


# =====================================================================
# POLYLINE (con bulge, senza bulge con fit, fallback)
# =====================================================================
def _convert_polyline(e, scale, layer_id, warnings) -> list[Entity]:
    vertices = list(e.vertices)
    if len(vertices) < 2:
        return []

    raw_points = [
        (v.dxf.location.x, v.dxf.location.y,
         float(getattr(v.dxf, "bulge", 0.0) or 0.0))
        for v in vertices
    ]
    has_bulge = any(abs(b) > 1e-12 for _, _, b in raw_points)
    closed = bool(e.is_closed)

    if has_bulge:
        path = _build_bulge_path(raw_points, closed, scale, layer_id)
        return [path] if path is not None else []

    # Nessun bulge: possibile arco o curva esplosa
    if len(raw_points) >= POLYLINE_ARC_FIT_THRESHOLD:
        pts_mm = [(x * scale, y * scale) for x, y, _ in raw_points]
        
        # 1. Tentativo fit circolare
        arc = fit_circle_arc(pts_mm, tolerance_mm=ARC_FIT_TOLERANCE_MM)
        if arc is not None:
            cx, cy, r, a0, a1, _fit_closed = arc
            if closed:
                a1 = a0 + 2.0 * math.pi
            segs = arc_to_bezier_segments(cx, cy, r, a0, a1)
            if segs:
                nodes: list[PathNode] = [PathNode(point=segs[0].p0)]
                append_bezier_segments_to_path(nodes, segs)
                if closed and len(nodes) > 1 and _points_close(nodes[0].point, nodes[-1].point):
                    last = nodes[-1]
                    if last.handle_in is not None:
                        nodes[0].handle_in = last.handle_in
                    nodes.pop()
                    return [PathEntity(layer_id=layer_id, nodes=nodes, closed=True)]
                return [PathEntity(layer_id=layer_id, nodes=nodes, closed=closed)]
        
        # 2. Fallback: fit generico di Bézier (solo se la polilinea è liscia)
        if is_smooth_for_bezier_fit(pts_mm):
            bezier_segs = fit_bezier_curve(pts_mm, tolerance_mm=ARC_FIT_TOLERANCE_MM)
            if bezier_segs:
                nodes = []
                for (p0, p1, p2, p3) in bezier_segs:
                    if not nodes:
                        nodes.append(PathNode(point=p0))
                    prev = nodes[-1]
                    prev.handle_out = (p1[0] - prev.point[0], p1[1] - prev.point[1])
                    nodes.append(PathNode(point=p3, handle_in=(p2[0] - p3[0], p2[1] - p3[1])))
                    
                if closed and len(nodes) > 1 and _points_close(nodes[0].point, nodes[-1].point):
                    last = nodes[-1]
                    if last.handle_in is not None:
                        nodes[0].handle_in = last.handle_in
                    nodes.pop()
                    return [PathEntity(layer_id=layer_id, nodes=nodes, closed=True)]
                return [PathEntity(layer_id=layer_id, nodes=nodes, closed=closed)]
            
        warnings.append(
            f"POLYLINE con {len(raw_points)} vertici: non riconosciuta come "
            "curva (fit circolare e fit Bézier falliti). Importata come polilinea."
        )

    pts_mm = [(x * scale, y * scale) for x, y, _ in raw_points]
    return [PolylineEntity(layer_id=layer_id, points=pts_mm, closed=closed)]


# =====================================================================
# Bulge → PathEntity (LWPOLYLINE / POLYLINE con bulge)
# =====================================================================
def _build_bulge_path(
    raw_points: list[tuple[float, float, float]],
    closed: bool,
    scale: float,
    layer_id: str,
) -> PathEntity | None:
    n = len(raw_points)
    if n < 2:
        return None

    segments: list[tuple] = []
    for i in range(n if closed else n - 1):
        p1 = (raw_points[i][0] * scale, raw_points[i][1] * scale)
        p2 = (raw_points[(i + 1) % n][0] * scale, raw_points[(i + 1) % n][1] * scale)
        bulge = float(raw_points[i][2]) if len(raw_points[i]) > 2 else 0.0
        if abs(bulge) < 1e-12:
            segments.append(("line", p1, p2))
        else:
            segments.append(("arc", p1, p2, bulge))

    if not segments:
        return None

    nodes: list[PathNode] = [PathNode(point=segments[0][1])]
    for item in segments:
        if item[0] == "line":
            nodes.append(PathNode(point=item[2]))
        else:
            _, p1, p2, bulge = item
            arc_segs = _bulge_to_bezier_segments(p1, p2, bulge)
            if arc_segs:
                append_bezier_segments_to_path(nodes, arc_segs)

    if closed and len(nodes) > 1 and _points_close(nodes[0].point, nodes[-1].point):
        last = nodes[-1]
        if last.handle_in is not None:
            nodes[0].handle_in = last.handle_in
        nodes.pop()

    return PathEntity(layer_id=layer_id, nodes=nodes, closed=closed)


def _bulge_to_bezier_segments(p1, p2, bulge):
    if abs(bulge) < 1e-12:
        return []
    alpha = 4.0 * math.atan(bulge)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    chord = math.hypot(dx, dy)
    if chord < 1e-12:
        return []
    sin_half = math.sin(alpha / 2.0)
    if abs(sin_half) < 1e-12:
        return []
    radius = chord / (2.0 * sin_half)
    d = radius * math.cos(alpha / 2.0)
    phi = math.atan2(dy, dx)
    perp = (-math.sin(phi), math.cos(phi))
    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    cx = mid[0] + d * perp[0]
    cy = mid[1] + d * perp[1]
    r_abs = abs(radius)
    a_start = math.atan2(p1[1] - cy, p1[0] - cx)
    return arc_to_bezier_segments(cx, cy, r_abs, a_start, a_start + alpha)


# =====================================================================
# CIRCLE / ARC / ELLIPSE / SPLINE / INSERT
# =====================================================================
def _convert_circle(e, scale, layer_id, warnings) -> list[Entity]:
    c = e.dxf.center
    return [CircleEntity(
        layer_id=layer_id,
        cx=c.x * scale, cy=c.y * scale, r=e.dxf.radius * scale,
    )]


def _convert_arc(e, scale, layer_id, warnings) -> list[Entity]:
    c = e.dxf.center
    r = e.dxf.radius * scale
    a0 = math.radians(e.dxf.start_angle)
    a1 = math.radians(e.dxf.end_angle)
    sweep = (a1 - a0) % (2.0 * math.pi)
    if sweep <= 1e-9:
        sweep = 2.0 * math.pi
    segs = arc_to_bezier_segments(c.x * scale, c.y * scale, r, a0, a0 + sweep)
    if not segs:
        return []
    nodes: list[PathNode] = [PathNode(point=segs[0].p0)]
    append_bezier_segments_to_path(nodes, segs)
    is_full = abs(sweep - 2.0 * math.pi) < 1e-6
    if is_full and _points_close(nodes[0].point, nodes[-1].point):
        last = nodes[-1]
        if last.handle_in is not None:
            nodes[0].handle_in = last.handle_in
        nodes.pop()
        return [PathEntity(layer_id=layer_id, nodes=nodes, closed=True)]
    return [PathEntity(layer_id=layer_id, nodes=nodes, closed=False)]


def _convert_ellipse(e, scale, layer_id, warnings) -> list[Entity]:
    c = e.dxf.center
    major = e.dxf.major_axis
    ratio = float(e.dxf.ratio)
    start = float(e.dxf.start_param)
    end = float(e.dxf.end_param)
    a = math.hypot(major.x, major.y) * scale
    b = a * ratio
    rotation = math.atan2(major.y, major.x)
    sweep = (end - start) % (2.0 * math.pi)
    is_full = abs(sweep) < 1e-9 or abs(sweep - 2.0 * math.pi) < 1e-6
    if is_full:
        sweep = 2.0 * math.pi
    segs = elliptical_arc_to_bezier_segments(
        c.x * scale, c.y * scale, a, b, rotation, start, start + sweep,
    )
    if not segs:
        return []
    nodes: list[PathNode] = [PathNode(point=segs[0].p0)]
    append_bezier_segments_to_path(nodes, segs)
    if is_full and _points_close(nodes[0].point, nodes[-1].point):
        last = nodes[-1]
        if last.handle_in is not None:
            nodes[0].handle_in = last.handle_in
        nodes.pop()
        return [PathEntity(layer_id=layer_id, nodes=nodes, closed=True)]
    return [PathEntity(layer_id=layer_id, nodes=nodes, closed=False)]


def _convert_spline(e, scale, layer_id, warnings) -> list[Entity]:
    try:
        bspline = e.construction_tool()
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"SPLINE non interpretabile: {exc}")
        return []

    try:
        bezier_list = list(bspline.bezier_decomposition())
    except Exception:  # noqa: BLE001
        bezier_list = []

    if (
        bezier_list
        and len(bezier_list) <= SPLINE_MAX_SEGMENTS
        and all(len(getattr(b, "control_points", [])) == 4 for b in bezier_list)
    ):
        return _spline_from_bezier_decomposition(bezier_list, scale, layer_id)

    fit = _spline_fit_hermite(bspline, scale, layer_id, SPLINE_MAX_SEGMENTS)
    if fit is not None:
        return fit

    try:
        tol_uu = 1.0 / max(scale, 1e-12)
        pts_uu = [(p.x, p.y) for p in e.flattening(distance=tol_uu)]
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"SPLINE flattening fallito: {exc}")
        return []
    if len(pts_uu) < 2:
        return []
    pts_mm = [(x * scale, y * scale) for (x, y) in pts_uu]
    return [PolylineEntity(layer_id=layer_id, points=pts_mm, closed=False)]


def _spline_from_bezier_decomposition(bezier_list, scale, layer_id) -> list[Entity]:
    nodes: list[PathNode] = []
    for b in bezier_list:
        p0, p1, p2, p3 = [(cp.x * scale, cp.y * scale) for cp in b.control_points]
        if not nodes:
            nodes.append(PathNode(point=p0))
        prev = nodes[-1]
        prev.handle_out = (p1[0] - prev.point[0], p1[1] - prev.point[1])
        nodes.append(PathNode(point=p3, handle_in=(p2[0] - p3[0], p2[1] - p3[1])))
    if len(nodes) < 2:
        return []
    closed = _points_close(nodes[0].point, nodes[-1].point)
    if closed:
        last = nodes[-1]
        if last.handle_in is not None:
            nodes[0].handle_in = last.handle_in
        nodes.pop()
    return [PathEntity(layer_id=layer_id, nodes=nodes, closed=closed)]


def _spline_fit_hermite(bspline, scale, layer_id, max_segments) -> list[Entity] | None:
    n = max(1, int(max_segments))
    eps = 1e-4
    try:
        pts_uu = [bspline.point(i / n) for i in range(n + 1)]
    except Exception:  # noqa: BLE001
        return None
    if len(pts_uu) < 2:
        return None

    nodes: list[PathNode] = [PathNode(point=(pts_uu[0].x * scale, pts_uu[0].y * scale))]
    for i in range(n):
        t0 = i / n
        t1 = (i + 1) / n
        dt = t1 - t0
        try:
            d0 = (bspline.point(t0 + eps) - bspline.point(t0)) / eps
            d1 = (bspline.point(t1) - bspline.point(t1 - eps)) / eps
            d0x, d0y = d0.x, d0.y
            d1x, d1y = d1.x, d1.y
        except Exception:  # noqa: BLE001
            d0x = d1x = pts_uu[i + 1].x - pts_uu[i].x
            d0y = d1y = pts_uu[i + 1].y - pts_uu[i].y

        p0_pt, p3_pt = pts_uu[i], pts_uu[i + 1]
        p1_pt = (p0_pt.x + d0x * dt / 3.0, p0_pt.y + d0y * dt / 3.0)
        p2_pt = (p3_pt.x - d1x * dt / 3.0, p3_pt.y - d1y * dt / 3.0)

        p0_mm = (p0_pt.x * scale, p0_pt.y * scale)
        p1_mm = (p1_pt[0] * scale, p1_pt[1] * scale)
        p2_mm = (p2_pt[0] * scale, p2_pt[1] * scale)
        p3_mm = (p3_pt.x * scale, p3_pt.y * scale)

        prev = nodes[-1]
        prev.handle_out = (p1_mm[0] - p0_mm[0], p1_mm[1] - p0_mm[1])
        nodes.append(PathNode(point=p3_mm, handle_in=(p2_mm[0] - p3_mm[0], p2_mm[1] - p3_mm[1])))

    if len(nodes) < 2:
        return None
    closed = _points_close(nodes[0].point, nodes[-1].point)
    if closed:
        last = nodes[-1]
        if last.handle_in is not None:
            nodes[0].handle_in = last.handle_in
        nodes.pop()
    return [PathEntity(layer_id=layer_id, nodes=nodes, closed=closed)]


def _convert_insert(e, scale, layer_id, warnings) -> list[Entity]:
    try:
        virtual = list(e.virtual_entities())
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"INSERT: espansione fallita: {exc}")
        return []
    entities: list[Entity] = []
    for sub in virtual:
        entities.extend(_convert_entity(sub, scale, layer_id, warnings))
    return entities


_HANDLERS = {
    "LINE": _convert_line,
    "LWPOLYLINE": _convert_lwpolyline,
    "POLYLINE": _convert_polyline,
    "CIRCLE": _convert_circle,
    "ARC": _convert_arc,
    "ELLIPSE": _convert_ellipse,
    "SPLINE": _convert_spline,
    "INSERT": _convert_insert,
}


def _points_close(a, b, tol=1e-6) -> bool:
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol