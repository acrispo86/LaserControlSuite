"""Importatore SVG → entità del core.

Usa ``svgpathtools`` per il parsing di ``<path>`` e forme base. Le unità
vengono lette da ``width``/``height`` (con suffisso mm/cm/in/px) e dalla
``viewBox``; il sistema di coordinate SVG (Y-down) viene convertito nel
sistema del core (Y-up) traslando di ``height_mm``.

Limiti noti MVP:
  - I ``transform`` sui gruppi ``<g>`` non vengono applicati (solo quelli
    direttamente sul path).
  - I ``text`` SVG non sono convertiti (in futuro).
  - Gli archi di ellisse sono approssimati con segmenti.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from svgpathtools import Line, CubicBezier, QuadraticBezier, Arc, Path as SvgPath, parse_path

from lasercontrolsuite.cad.io.units import parse_svg_length, svg_user_unit_to_mm
from lasercontrolsuite.core.entities import (
    CircleEntity,
    EllipseEntity,
    Entity,
    PolylineEntity,
)
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.path import PathEntity, PathNode


@dataclass
class SvgImportResult:
    """Risultato di un import SVG."""

    entities: list[Entity] = field(default_factory=list)
    layer_id: str = ""
    source_path: str = ""
    #: Millimetri per unità utente SVG
    unit_scale: float = 1.0
    width_mm: float = 0.0
    height_mm: float = 0.0
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


# =====================================================================
# API principale
# =====================================================================
def import_svg(path: str | Path, layer_id: str) -> SvgImportResult:
    """Importa un file SVG.

    Args:
        path: percorso del file SVG.
        layer_id: id del layer del core in cui inserire le entità.

    Returns:
        ``SvgImportResult`` con entità in mm, in coordinate scena Y-up.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File SVG non trovato: {path}")

    # Parsing XML per metadati (width/height/viewBox)
    try:
        tree = ET.parse(str(p))
        root = tree.getroot()
    except ET.ParseError as exc:
        raise ValueError(f"SVG malformato: {exc}") from exc

    width_attr = root.get("width")
    height_attr = root.get("height")
    viewbox = root.get("viewBox")

    width_mm = parse_svg_length(width_attr, default_mm=0.0)
    height_mm = parse_svg_length(height_attr, default_mm=0.0)

    if viewbox:
        parts = [float(v) for v in re.split(r"[ ,]+", viewbox.strip()) if v]
        if len(parts) != 4:
            raise ValueError(f"viewBox non valido: {viewbox!r}")
        _vb_x, _vb_y, vb_w, vb_h = parts
    else:
        vb_w = vb_h = 0.0

    if vb_w > 0 and width_mm > 0:
        scale = width_mm / vb_w
    elif width_mm > 0 and vb_w == 0:
        # width in mm ma senza viewBox: le coordinate utente sono mm
        scale = 1.0
    else:
        # fallback: unità utente (px CSS)
        scale = svg_user_unit_to_mm()
        if vb_w > 0:
            width_mm = vb_w * scale
        if vb_h > 0:
            height_mm = vb_h * scale

    if height_mm <= 0 and vb_h > 0:
        height_mm = vb_h * scale

    result = SvgImportResult(
        layer_id=layer_id,
        source_path=str(p),
        unit_scale=scale,
        width_mm=width_mm,
        height_mm=height_mm,
    )

    # Iterazione elementi: <path> + forme base
    _walk_svg(root, scale, height_mm, layer_id, result)

    return result


# =====================================================================
# Walk dell'albero SVG
# =====================================================================
def _walk_svg(node, scale: float, height_mm: float, layer_id: str, result: SvgImportResult) -> None:
    tag = _local_tag(node.tag)

    # Le trasformazioni sui gruppi sono ignorate nell'MVP; le note vengono
    # comunque emesse se presenti.
    if tag in ("g", "svg"):
        if node.get("transform"):
            result.warnings.append(
                f"<{tag} transform=...> ignorato (non supportato nell'MVP)."
            )
        for child in node:
            _walk_svg(child, scale, height_mm, layer_id, result)
        return

    if tag == "path":
        d = node.get("d", "")
        if not d:
            return
        try:
            svg_path = parse_path(d)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"<path> parse fallito: {exc}")
            return
        entity = _svg_path_to_path_entity(svg_path, scale, height_mm, layer_id)
        if entity is not None:
            result.entities.append(entity)
        return

    if tag == "rect":
        entity = _shape_rect(node, scale, height_mm, layer_id)
        if entity is not None:
            result.entities.append(entity)
        return

    if tag == "circle":
        entity = _shape_circle(node, scale, height_mm, layer_id)
        if entity is not None:
            result.entities.append(entity)
        return

    if tag == "ellipse":
        entity = _shape_ellipse(node, scale, height_mm, layer_id)
        if entity is not None:
            result.entities.append(entity)
        return

    if tag in ("line", "polyline", "polygon"):
        entity = _shape_line_poly(node, tag, scale, height_mm, layer_id)
        if entity is not None:
            result.entities.append(entity)
        return

    # altri tag: ignora silenziosamente (text, image, defs, ...)
    return


def _local_tag(tag: str) -> str:
    """Rimuove il namespace da un tag (``{http://...}path`` → ``path``)."""
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


# =====================================================================
# Conversioni
# =====================================================================
def _px_to_mm(x: float, y: float, scale: float, height_mm: float) -> tuple[float, float]:
    """Converti (x, y) SVG in coordinate scena (mm, Y-up)."""
    return (x * scale, height_mm - y * scale)


def _svg_path_to_path_entity(
    svg_path: SvgPath, scale: float, height_mm: float, layer_id: str
) -> PathEntity | None:
    """Converte un ``svgpathtools.Path`` in ``PathEntity``.

    Segmenti lineari → nodi corner. Bézier cubiche → nodi con handle.
    Archi → approssimati con corner nodes.
    """
    segments = list(svg_path)
    if not segments:
        return None

    nodes: list[PathNode] = []
    start_point = segments[0].start
    x0, y0 = _px_to_mm(start_point.real, start_point.imag, scale, height_mm)
    nodes.append(PathNode((x0, y0)))

    for seg in segments:
        if isinstance(seg, Line):
            ex, ey = _px_to_mm(seg.end.real, seg.end.imag, scale, height_mm)
            nodes.append(PathNode((ex, ey)))
        elif isinstance(seg, CubicBezier):
            c1 = seg.control1
            c2 = seg.control2
            end = seg.end
            h_out_rel = _handle_rel(
                start_pt=(nodes[-1].point[0], nodes[-1].point[1]),
                abs_pt=(c1.real * scale, height_mm - c1.imag * scale),
            )
            ex, ey = _px_to_mm(end.real, end.imag, scale, height_mm)
            h_in_rel = _handle_rel(
                start_pt=(ex, ey),
                abs_pt=(c2.real * scale, height_mm - c2.imag * scale),
            )
            # Aggiorna handle_out del nodo precedente
            nodes[-1].handle_out = h_out_rel
            nodes.append(PathNode(point=(ex, ey), handle_in=h_in_rel))
        elif isinstance(seg, QuadraticBezier):
            # Converte quadratica in cubica: c1 = p0 + 2/3 (q - p0), c2 = p3 + 2/3 (q - p3)
            p0 = seg.start
            q = seg.control
            p3 = seg.end
            c1 = p0 + (2.0 / 3.0) * (q - p0)
            c2 = p3 + (2.0 / 3.0) * (q - p3)
            h_out_rel = _handle_rel(
                start_pt=(nodes[-1].point[0], nodes[-1].point[1]),
                abs_pt=(c1.real * scale, height_mm - c1.imag * scale),
            )
            ex, ey = _px_to_mm(p3.real, p3.imag, scale, height_mm)
            h_in_rel = _handle_rel(
                start_pt=(ex, ey),
                abs_pt=(c2.real * scale, height_mm - c2.imag * scale),
            )
            nodes[-1].handle_out = h_out_rel
            nodes.append(PathNode(point=(ex, ey), handle_in=h_in_rel))
        elif isinstance(seg, Arc):
            # Approssima con N corner node lungo l'arco
            n = max(8, int(abs(seg.delta) * 180 / math.pi / 4))  # ~4° per step
            for i in range(1, n + 1):
                t = i / n
                pt = seg.point(t)
                x, y = _px_to_mm(pt.real, pt.imag, scale, height_mm)
                nodes.append(PathNode((x, y)))
        else:
            # Fallback: sample estremi come linee
            n = 16
            for i in range(1, n + 1):
                t = i / n
                pt = seg.point(t)
                x, y = _px_to_mm(pt.real, pt.imag, scale, height_mm)
                nodes.append(PathNode((x, y)))

    if len(nodes) < 2:
        return None

    # Closed path se start == end
    closed = _points_close(nodes[0].point, nodes[-1].point)
    if closed:
        nodes.pop()  # rimuovi duplicato finale

    return PathEntity(layer_id=layer_id, nodes=nodes, closed=closed)


def _handle_rel(
    start_pt: tuple[float, float], abs_pt: tuple[float, float]
) -> tuple[float, float]:
    return (abs_pt[0] - start_pt[0], abs_pt[1] - start_pt[1])


def _points_close(
    a: tuple[float, float], b: tuple[float, float], tol: float = 1e-6
) -> bool:
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def _parse_float(v: str | None, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _shape_rect(node, scale: float, height_mm: float, layer_id: str) -> Entity | None:
    x = _parse_float(node.get("x"), 0.0)
    y = _parse_float(node.get("y"), 0.0)
    w = _parse_float(node.get("width"), 0.0)
    h = _parse_float(node.get("height"), 0.0)
    if w <= 0 or h <= 0:
        return None
    # Angoli in coordinate scena
    x0, y0 = _px_to_mm(x, y, scale, height_mm)          # top-left SVG → alto sx scena
    x1, y1 = _px_to_mm(x + w, y + h, scale, height_mm)  # bottom-right → basso dx scena
    # Normalizza
    left, right = sorted((x0, x1))
    bottom, top = sorted((y0, y1))
    pts = [
        (left, bottom),
        (right, bottom),
        (right, top),
        (left, top),
    ]
    return PolylineEntity(layer_id=layer_id, points=pts, closed=True)


def _shape_circle(node, scale: float, height_mm: float, layer_id: str) -> Entity | None:
    cx = _parse_float(node.get("cx"), 0.0)
    cy = _parse_float(node.get("cy"), 0.0)
    r = _parse_float(node.get("r"), 0.0)
    if r <= 0:
        return None
    scx, scy = _px_to_mm(cx, cy, scale, height_mm)
    return CircleEntity(layer_id=layer_id, cx=scx, cy=scy, r=r * scale)


def _shape_ellipse(node, scale: float, height_mm: float, layer_id: str) -> Entity | None:
    cx = _parse_float(node.get("cx"), 0.0)
    cy = _parse_float(node.get("cy"), 0.0)
    rx = _parse_float(node.get("rx"), 0.0)
    ry = _parse_float(node.get("ry"), 0.0)
    if rx <= 0 or ry <= 0:
        return None
    scx, scy = _px_to_mm(cx, cy, scale, height_mm)
    return EllipseEntity(layer_id=layer_id, cx=scx, cy=scy, rx=rx * scale, ry=ry * scale)


def _shape_line_poly(node, tag: str, scale: float, height_mm: float, layer_id: str) -> Entity | None:
    if tag == "line":
        x1 = _parse_float(node.get("x1"))
        y1 = _parse_float(node.get("y1"))
        x2 = _parse_float(node.get("x2"))
        y2 = _parse_float(node.get("y2"))
        pts_svg = [(x1, y1), (x2, y2)]
        closed = False
    else:
        pts_attr = node.get("points", "").strip()
        if not pts_attr:
            return None
        parts = re.split(r"[ ,]+", pts_attr)
        if len(parts) % 2 != 0:
            return None
        nums = []
        for s in parts:
            try:
                nums.append(float(s))
            except ValueError:
                return None
        pts_svg = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
        closed = tag == "polygon"

    if len(pts_svg) < 2:
        return None

    pts_mm = [_px_to_mm(x, y, scale, height_mm) for (x, y) in pts_svg]
    return PolylineEntity(layer_id=layer_id, points=pts_mm, closed=closed)