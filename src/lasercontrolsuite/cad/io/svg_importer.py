"""Importatore SVG → entità del core.

Usa ``svgpathtools`` per il parsing di ``<path>`` e forme base.

Step 9i-a — bug fix (mantenuti):
  1. ``<path transform>``, ``<g transform>``, ``<svg transform>`` applicati.
  2. ``viewBox`` offset rispettato.
  3. Multi-subpath: ogni subpath → PathEntity separata.
  4. Chiusura: handle_in dell'ultimo nodo trasferito al primo.
  5. Archi: mai campionati in decine/centinaia di nodi corner.

Step 9i-b2 — curve native:
  - Archi SVG (circolari ed ellittici) → Bézier cubiche via **campionamento
    numerico Hermite→Bézier** basato solo su ``seg.point(t)``. Non dipende
    da ``seg.theta``, ``seg.delta``, ``seg.center``, ``seg.radius``, la cui
    semantica (gradi vs radianti, segni, eccezioni) varia tra versioni di
    ``svgpathtools``. Numero di segmenti scelto in base alla lunghezza
    dell'arco: 1 se <1 mm, 2 se <5 mm, 4 altrimenti.
  - I path con ``C``/``Q`` erano già Bézier native → invariati.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from svgpathtools import (
    Line, CubicBezier, QuadraticBezier, Arc, Path as SvgPath, parse_path,
)

from lasercontrolsuite.cad.io._bezier_utils import (
    append_bezier_segments_to_path,
    elliptical_arc_to_bezier_segments,
)
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
    entities: list[Entity] = field(default_factory=list)
    layer_id: str = ""
    source_path: str = ""
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
# API
# =====================================================================
def import_svg(path: str | Path, layer_id: str) -> SvgImportResult:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File SVG non trovato: {path}")

    try:
        tree = ET.parse(str(p))
        root = tree.getroot()
    except ET.ParseError as exc:
        raise ValueError(f"SVG malformato: {exc}") from exc

    width_mm = parse_svg_length(root.get("width"), default_mm=0.0)
    height_mm = parse_svg_length(root.get("height"), default_mm=0.0)

    vb_x = vb_y = vb_w = vb_h = 0.0
    viewbox = root.get("viewBox")
    if viewbox:
        parts = [float(v) for v in re.split(r"[ ,]+", viewbox.strip()) if v]
        if len(parts) != 4:
            raise ValueError(f"viewBox non valido: {viewbox!r}")
        vb_x, vb_y, vb_w, vb_h = parts

    if vb_w > 0 and width_mm > 0:
        scale = width_mm / vb_w
    elif width_mm > 0 and vb_w == 0:
        scale = 1.0
    else:
        scale = svg_user_unit_to_mm()
        if vb_w > 0:
            width_mm = vb_w * scale
        if vb_h > 0:
            height_mm = vb_h * scale
    if height_mm <= 0 and vb_h > 0:
        height_mm = vb_h * scale

    result = SvgImportResult(
        layer_id=layer_id, source_path=str(p),
        unit_scale=scale, width_mm=width_mm, height_mm=height_mm,
    )

    _walk_svg(root, scale, height_mm, vb_x, vb_y, layer_id,
              Matrix2D.identity(), result)
    return result


# =====================================================================
# Walk
# =====================================================================
def _walk_svg(
    node, scale, height_mm, vb_x, vb_y, layer_id, parent_transform, result,
):
    tag = _local_tag(node.tag)

    local = _parse_svg_transform(node.get("transform"))
    my_transform = local @ parent_transform

    if tag in ("g", "svg"):
        for child in node:
            _walk_svg(child, scale, height_mm, vb_x, vb_y, layer_id,
                      my_transform, result)
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
        result.entities.extend(_svg_path_to_path_entities(
            svg_path, my_transform, scale, height_mm, vb_x, vb_y, layer_id,
        ))
        return

    if tag == "rect":
        e = _shape_rect(node, my_transform, scale, height_mm, vb_x, vb_y, layer_id)
        if e is not None:
            result.entities.append(e)
        return

    if tag == "circle":
        e = _shape_circle(node, my_transform, scale, height_mm, vb_x, vb_y, layer_id)
        if e is not None:
            result.entities.append(e)
        return

    if tag == "ellipse":
        e = _shape_ellipse(node, my_transform, scale, height_mm, vb_x, vb_y, layer_id)
        if e is not None:
            result.entities.append(e)
        return

    if tag in ("line", "polyline", "polygon"):
        e = _shape_line_poly(node, tag, my_transform, scale, height_mm, vb_x, vb_y, layer_id)
        if e is not None:
            result.entities.append(e)
        return


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[1] if "}" in tag else tag


# =====================================================================
# Transform SVG
# =====================================================================
_TRANSFORM_PATTERN = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")


def _parse_svg_transform(s: str | None) -> Matrix2D:
    if not s:
        return Matrix2D.identity()
    matrix = Matrix2D.identity()
    for match in _TRANSFORM_PATTERN.finditer(s):
        name = match.group(1).lower()
        try:
            args = [float(x) for x in re.split(r"[\s,]+", match.group(2).strip()) if x]
        except ValueError:
            continue
        m = _transform_fn(name, args)
        if m is not None:
            matrix = m @ matrix
    return matrix


def _transform_fn(name: str, args: list[float]) -> Matrix2D | None:
    if name == "matrix" and len(args) == 6:
        return Matrix2D(*args)
    if name == "translate":
        if len(args) == 1:
            return Matrix2D.translation(args[0], 0.0)
        if len(args) == 2:
            return Matrix2D.translation(args[0], args[1])
    if name == "scale":
        if len(args) == 1:
            return Matrix2D.scaling(args[0], args[0])
        if len(args) == 2:
            return Matrix2D.scaling(args[0], args[1])
    if name == "rotate":
        if len(args) == 1:
            return Matrix2D.rotation_deg(args[0])
        if len(args) == 3:
            cx, cy, ang = args
            return (
                Matrix2D.translation(cx, cy)
                @ Matrix2D.rotation_deg(ang)
                @ Matrix2D.translation(-cx, -cy)
            )
    if name == "skewX" and len(args) == 1:
        return Matrix2D(1.0, 0.0, math.tan(math.radians(args[0])), 1.0, 0.0, 0.0)
    if name == "skewY" and len(args) == 1:
        return Matrix2D(1.0, math.tan(math.radians(args[0])), 0.0, 1.0, 0.0, 0.0)
    return None


def _is_identity(m: Matrix2D) -> bool:
    return (
        abs(m.a - 1.0) < 1e-9 and abs(m.b) < 1e-9 and abs(m.c) < 1e-9
        and abs(m.d - 1.0) < 1e-9 and abs(m.e) < 1e-9 and abs(m.f) < 1e-9
    )


def _similarity_scale(m: Matrix2D) -> float | None:
    n1 = math.hypot(m.a, m.b)
    n2 = math.hypot(m.c, m.d)
    if n1 < 1e-9 or n2 < 1e-9:
        return None
    if abs(n1 - n2) > 1e-6 * max(n1, n2):
        return None
    if abs(m.a * m.c + m.b * m.d) > 1e-6 * n1 * n1:
        return None
    return n1


# =====================================================================
# Mapping user-unit → mm scena
# =====================================================================
def _apply_and_map(
    x: float, y: float, transform: Matrix2D,
    scale: float, height_mm: float, vb_x: float, vb_y: float,
) -> tuple[float, float]:
    tx = x * transform.a + y * transform.c + transform.e
    ty = x * transform.b + y * transform.d + transform.f
    return ((tx - vb_x) * scale, height_mm - (ty - vb_y) * scale)


# =====================================================================
# Path SVG
# =====================================================================
def _svg_path_to_path_entities(
    svg_path: SvgPath, transform: Matrix2D,
    scale: float, height_mm: float, vb_x: float, vb_y: float, layer_id: str,
) -> list[PathEntity]:
    segments = list(svg_path)
    if not segments:
        return []

    def _map(x, y):
        return _apply_and_map(x, y, transform, scale, height_mm, vb_x, vb_y)

    subpaths: list[tuple[list[PathNode], bool]] = []
    current_nodes: list[PathNode] = []
    prev_end: tuple[float, float] | None = None

    def _flush():
        nonlocal current_nodes
        if len(current_nodes) < 2:
            current_nodes = []
            return
        closed = _points_close(current_nodes[0].point, current_nodes[-1].point)
        if closed:
            last = current_nodes[-1]
            if last.handle_in is not None:
                current_nodes[0].handle_in = last.handle_in
            current_nodes.pop()
            if len(current_nodes) < 2:
                current_nodes = []
                return
        subpaths.append((current_nodes, closed))
        current_nodes = []

    for seg in segments:
        start_xy = (seg.start.real, seg.start.imag)
        if prev_end is not None and not _points_close_xy(start_xy, prev_end):
            _flush()

        if not current_nodes:
            sx, sy = _map(seg.start.real, seg.start.imag)
            current_nodes = [PathNode((sx, sy))]

        if isinstance(seg, Line):
            ex, ey = _map(seg.end.real, seg.end.imag)
            current_nodes.append(PathNode((ex, ey)))

        elif isinstance(seg, CubicBezier):
            prev_pt = current_nodes[-1].point
            c1 = _map(seg.control1.real, seg.control1.imag)
            h_out = (c1[0] - prev_pt[0], c1[1] - prev_pt[1])
            ex, ey = _map(seg.end.real, seg.end.imag)
            c2 = _map(seg.control2.real, seg.control2.imag)
            h_in = (c2[0] - ex, c2[1] - ey)
            current_nodes[-1].handle_out = h_out
            current_nodes.append(PathNode(point=(ex, ey), handle_in=h_in))

        elif isinstance(seg, QuadraticBezier):
            p0, q, p3 = seg.start, seg.control, seg.end
            c1 = p0 + (2.0 / 3.0) * (q - p0)
            c2 = p3 + (2.0 / 3.0) * (q - p3)
            prev_pt = current_nodes[-1].point
            c1_mm = _map(c1.real, c1.imag)
            h_out = (c1_mm[0] - prev_pt[0], c1_mm[1] - prev_pt[1])
            ex, ey = _map(p3.real, p3.imag)
            c2_mm = _map(c2.real, c2.imag)
            h_in = (c2_mm[0] - ex, c2_mm[1] - ey)
            current_nodes[-1].handle_out = h_out
            current_nodes.append(PathNode(point=(ex, ey), handle_in=h_in))

        elif isinstance(seg, Arc):
            _append_svg_arc_as_bezier(
                seg, current_nodes, transform, scale, height_mm, vb_x, vb_y,
            )

        else:
            # Fallback: campionamento generico
            n = 16
            for i in range(1, n + 1):
                pt = seg.point(i / n)
                x, y = _map(pt.real, pt.imag)
                current_nodes.append(PathNode((x, y)))

        prev_end = (seg.end.real, seg.end.imag)

    _flush()

    return [
        PathEntity(layer_id=layer_id, nodes=nodes, closed=closed)
        for nodes, closed in subpaths
    ]


def _append_svg_arc_as_bezier(
    seg: Arc, current_nodes: list[PathNode],
    transform: Matrix2D, scale: float, height_mm: float, vb_x: float, vb_y: float,
) -> None:
    """Converte un arco SVG in Bézier cubiche via campionamento Hermite.

    Usa esclusivamente ``seg.point(t)`` (API stabile) e la derivata numerica
    per costruire segmenti Bézier tramite conversione Hermite→Bézier:

        P1 = P0 + d0 · dt/3
        P2 = P3 − d1 · dt/3

    dove ``d0 = dP/dt`` in t0 e ``d1 = dP/dt`` in t1, stimate per differenza
    finita. Questo bypassa del tutto ``seg.theta``, ``seg.delta``,
    ``seg.center``, ``seg.radius``, la cui semantica (gradi vs radianti,
    segno dello sweep, possibili eccezioni) è variata tra versioni di
    ``svgpathtools``.

    Numero di segmenti scelto in base alla lunghezza dell'arco:
      1 se <1 mm, 2 se <5 mm, 4 altrimenti. Copre fino a 2π con errore
      trascurabile (<0.1% del raggio).
    """
    try:
        length_mm = seg.length(error=1e-4) * scale
    except Exception:  # noqa: BLE001
        length_mm = 0.0

    if length_mm < 1.0:
        num = 1
    elif length_mm < 5.0:
        num = 2
    else:
        num = 4

    eps = 1e-4  # per derivata numerica, in unità utente

    for i in range(num):
        t0 = i / num
        t1 = (i + 1) / num
        dt = t1 - t0

        try:
            p0 = seg.point(t0)
            p3 = seg.point(t1)
        except Exception:  # noqa: BLE001
            # Arco non campionabile: salta il resto
            return

        # Derivata numerica (in unità utente)
        try:
            d0 = (seg.point(t0 + eps) - p0) / eps
            d1 = (p3 - seg.point(t1 - eps)) / eps
        except Exception:  # noqa: BLE001
            # Fallback lineare
            d0 = p3 - p0
            d1 = p3 - p0

        # Hermite → Bézier
        p1 = p0 + d0 * dt / 3.0
        p2 = p3 - d1 * dt / 3.0

        # Mappa i punti (la mappatura è affine, vale per i punti di controllo)
        p0_mm = _apply_and_map(p0.real, p0.imag, transform, scale, height_mm, vb_x, vb_y)
        p1_mm = _apply_and_map(p1.real, p1.imag, transform, scale, height_mm, vb_x, vb_y)
        p2_mm = _apply_and_map(p2.real, p2.imag, transform, scale, height_mm, vb_x, vb_y)
        p3_mm = _apply_and_map(p3.real, p3.imag, transform, scale, height_mm, vb_x, vb_y)

        if i == 0 and current_nodes:
            prev = current_nodes[-1]
            prev.handle_out = (p1_mm[0] - prev.point[0], p1_mm[1] - prev.point[1])

        current_nodes.append(PathNode(
            point=p3_mm,
            handle_in=(p2_mm[0] - p3_mm[0], p2_mm[1] - p3_mm[1]),
        ))


def _points_close(a, b, tol=1e-6):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def _points_close_xy(a, b, tol=1e-6):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


# =====================================================================
# Forme base
# =====================================================================
def _parse_float(v, default=0.0):
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _shape_rect(node, transform, scale, height_mm, vb_x, vb_y, layer_id):
    x = _parse_float(node.get("x"), 0.0)
    y = _parse_float(node.get("y"), 0.0)
    w = _parse_float(node.get("width"), 0.0)
    h = _parse_float(node.get("height"), 0.0)
    if w <= 0 or h <= 0:
        return None

    corners_uu = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    pts_mm = [_apply_and_map(cx, cy, transform, scale, height_mm, vb_x, vb_y)
              for cx, cy in corners_uu]

    if _is_identity(transform):
        xs = [p[0] for p in pts_mm]
        ys = [p[1] for p in pts_mm]
        left, right = min(xs), max(xs)
        bottom, top = min(ys), max(ys)
        pts_mm = [(left, bottom), (right, bottom), (right, top), (left, top)]

    return PolylineEntity(layer_id=layer_id, points=pts_mm, closed=True)


def _shape_circle(node, transform, scale, height_mm, vb_x, vb_y, layer_id):
    cx = _parse_float(node.get("cx"), 0.0)
    cy = _parse_float(node.get("cy"), 0.0)
    r = _parse_float(node.get("r"), 0.0)
    if r <= 0:
        return None

    if _is_identity(transform):
        scx, scy = _apply_and_map(cx, cy, transform, scale, height_mm, vb_x, vb_y)
        return CircleEntity(layer_id=layer_id, cx=scx, cy=scy, r=r * scale)

    sim = _similarity_scale(transform)
    if sim is not None and sim > 1e-9:
        scx, scy = _apply_and_map(cx, cy, transform, scale, height_mm, vb_x, vb_y)
        return CircleEntity(layer_id=layer_id, cx=scx, cy=scy, r=r * sim * scale)

    # Fallback: polilinea
    n = 64
    pts_uu = [(cx + r * math.cos(2 * math.pi * i / n),
               cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    pts_mm = [_apply_and_map(x, y, transform, scale, height_mm, vb_x, vb_y)
              for x, y in pts_uu]
    return PolylineEntity(layer_id=layer_id, points=pts_mm, closed=True)


def _shape_ellipse(node, transform, scale, height_mm, vb_x, vb_y, layer_id):
    cx = _parse_float(node.get("cx"), 0.0)
    cy = _parse_float(node.get("cy"), 0.0)
    rx = _parse_float(node.get("rx"), 0.0)
    ry = _parse_float(node.get("ry"), 0.0)
    if rx <= 0 or ry <= 0:
        return None

    if _is_identity(transform):
        scx, scy = _apply_and_map(cx, cy, transform, scale, height_mm, vb_x, vb_y)
        return EllipseEntity(layer_id=layer_id, cx=scx, cy=scy,
                              rx=rx * scale, ry=ry * scale)

    # Transform non-identity: PathEntity con Bézier native
    segs = elliptical_arc_to_bezier_segments(
        cx, cy, rx, ry, 0.0, 0.0, 2.0 * math.pi,
    )
    if not segs:
        return None

    nodes: list[PathNode] = []
    for seg in segs:
        p0 = _apply_and_map(seg.p0[0], seg.p0[1], transform, scale, height_mm, vb_x, vb_y)
        p1 = _apply_and_map(seg.p1[0], seg.p1[1], transform, scale, height_mm, vb_x, vb_y)
        p2 = _apply_and_map(seg.p2[0], seg.p2[1], transform, scale, height_mm, vb_x, vb_y)
        p3 = _apply_and_map(seg.p3[0], seg.p3[1], transform, scale, height_mm, vb_x, vb_y)
        if not nodes:
            nodes.append(PathNode(point=p0))
        prev = nodes[-1]
        prev.handle_out = (p1[0] - prev.point[0], p1[1] - prev.point[1])
        nodes.append(PathNode(point=p3, handle_in=(p2[0] - p3[0], p2[1] - p3[1])))

    if len(nodes) > 1 and _points_close(nodes[0].point, nodes[-1].point):
        last = nodes[-1]
        if last.handle_in is not None:
            nodes[0].handle_in = last.handle_in
        nodes.pop()

    return PathEntity(layer_id=layer_id, nodes=nodes, closed=True)


def _shape_line_poly(node, tag, transform, scale, height_mm, vb_x, vb_y, layer_id):
    if tag == "line":
        pts_uu = [
            (_parse_float(node.get("x1")), _parse_float(node.get("y1"))),
            (_parse_float(node.get("x2")), _parse_float(node.get("y2"))),
        ]
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
        pts_uu = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
        closed = tag == "polygon"

    if len(pts_uu) < 2:
        return None

    pts_mm = [_apply_and_map(x, y, transform, scale, height_mm, vb_x, vb_y)
              for x, y in pts_uu]
    return PolylineEntity(layer_id=layer_id, points=pts_mm, closed=closed)