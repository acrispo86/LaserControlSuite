"""
image_tracer.py - Tracciamento di immagini raster in vettori.

Due modalità:
  * outline     -> "traccia completa": contorni esterni e fori di ogni forma
  * centerline  -> "solo linea centrale": scheletro della forma (tratti sottili)

Dipendenze:  pip install numpy opencv-python scikit-image

Uso da codice:
    from image_tracer import trace_image, save_svg
    res = trace_image("logo.png", mode="centerline", prune=8)
    save_svg("logo.svg", res, dpi=254)

Uso da riga di comando:
    python image_tracer.py logo.png logo.svg --mode both --dpi 254
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field

import cv2
import numpy as np

try:
    from skimage.morphology import skeletonize as _sk_skeletonize
except ImportError:  # fallback: richiede opencv-contrib-python
    _sk_skeletonize = None


# --------------------------------------------------------------------------
# Strutture dati
# --------------------------------------------------------------------------
@dataclass
class Polyline:
    points: np.ndarray  # (N, 2) float, coordinate (x, y) in pixel
    closed: bool


@dataclass
class TraceResult:
    outlines: list[Polyline] = field(default_factory=list)
    centerlines: list[Polyline] = field(default_factory=list)
    size: tuple[int, int] = (0, 0)  # (larghezza, altezza) in pixel


# --------------------------------------------------------------------------
# Caricamento e binarizzazione
# --------------------------------------------------------------------------
def load_binary(
    path: str,
    threshold: int | None = None,
    invert: bool = False,
    blur: int = 0,
    max_side: int | None = None,
) -> np.ndarray:
    """
    Carica un'immagine e restituisce una maschera uint8 (255 = primo piano).
    Per default il primo piano è la parte SCURA dell'immagine.

    threshold : soglia 0-255; None = Otsu automatico
    invert    : se True il primo piano è la parte chiara
    blur      : raggio (dispari) di sfocatura gaussiana per ridurre il rumore
    max_side  : ridimensiona se il lato maggiore supera questo valore
    """
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(f"Impossibile leggere l'immagine: {path}")

    if img.ndim == 3 and img.shape[2] == 4:  # canale alpha -> sfondo bianco
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
        rgb = img[:, :, :3].astype(np.float32)
        img = (rgb * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if gray.dtype != np.uint8:
        gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    if max_side and max(gray.shape) > max_side:
        s = max_side / max(gray.shape)
        gray = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)

    if blur and blur > 1:
        k = blur if blur % 2 == 1 else blur + 1
        gray = cv2.GaussianBlur(gray, (k, k), 0)

    flag = cv2.THRESH_BINARY if invert else cv2.THRESH_BINARY_INV
    if threshold is None:
        _, mask = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)
    else:
        _, mask = cv2.threshold(gray, threshold, 255, flag)
    return mask


# --------------------------------------------------------------------------
# Traccia completa (contorni)
# --------------------------------------------------------------------------
def trace_outline(
    mask: np.ndarray, epsilon: float = 1.0, min_area: float = 4.0
) -> list[Polyline]:
    """
    Estrae i contorni (esterni e fori) di ogni forma.
    epsilon  : tolleranza di semplificazione (px); più alto = meno punti
    min_area : scarta macchie con area inferiore (px^2)
    """
    padded = np.pad(mask, 1)  # bordo vuoto: chiude le forme sul margine
    contours, _ = cv2.findContours(padded, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out: list[Polyline] = []
    for c in contours:
        if abs(cv2.contourArea(c)) < min_area:
            continue
        if epsilon > 0:
            c = cv2.approxPolyDP(c, epsilon, True)
        if len(c) < 3:
            continue
        pts = c.reshape(-1, 2).astype(float) - 1.0
        out.append(Polyline(pts, True))
    return out


# --------------------------------------------------------------------------
# Linea centrale (scheletro)
# --------------------------------------------------------------------------
_ORTH = ((-1, 0), (1, 0), (0, -1), (0, 1))
_DIAG = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def _skeletonize(mask: np.ndarray) -> np.ndarray:
    binary = mask > 0
    if _sk_skeletonize is not None:
        return _sk_skeletonize(binary)
    if hasattr(cv2, "ximgproc"):
        return cv2.ximgproc.thinning(mask) > 0
    raise ImportError("Installa scikit-image (pip install scikit-image)")


def _neighbors(p, pix):
    """Vicini 8-connessi, scartando le diagonali ridondanti agli angoli
    (evita falsi incroci nelle scalette dello scheletro)."""
    y, x = p
    out = []
    for dy, dx in _ORTH:
        q = (y + dy, x + dx)
        if q in pix:
            out.append(q)
    for dy, dx in _DIAG:
        q = (y + dy, x + dx)
        if q in pix and (y + dy, x) not in pix and (y, x + dx) not in pix:
            out.append(q)
    return out


def _skeleton_to_paths(skel: np.ndarray, prune: int = 0) -> list[list[tuple[int, int]]]:
    """Converte lo scheletro in polilinee (spezzate agli incroci)."""
    ys, xs = np.nonzero(skel)
    pix = set(zip(ys.tolist(), xs.tolist()))
    nbrs = {p: _neighbors(p, pix) for p in pix}
    is_node = {p: len(n) != 2 for p, n in nbrs.items()}
    used: set = set()

    def key(a, b):
        return (a, b) if a < b else (b, a)

    def walk(start, nxt):
        path = [start, nxt]
        used.add(key(start, nxt))
        prev, cur = start, nxt
        while not is_node[cur] and cur != start:
            cand = [q for q in nbrs[cur] if q != prev and key(cur, q) not in used]
            if not cand:
                break
            nx = cand[0]
            used.add(key(cur, nx))
            path.append(nx)
            prev, cur = cur, nx
        return path

    paths = []
    for p in pix:  # prima i rami che partono da nodi (estremi / incroci)
        if is_node[p]:
            for q in nbrs[p]:
                if key(p, q) not in used:
                    paths.append(walk(p, q))
    for p in pix:  # poi gli anelli chiusi senza nodi
        if not is_node[p]:
            for q in nbrs[p]:
                if key(p, q) not in used:
                    paths.append(walk(p, q))

    if prune > 0:  # elimina i "peletti": rami corti che finiscono in un estremo
        deg = {p: len(n) for p, n in nbrs.items()}
        kept = []
        for path in paths:
            a, b = path[0], path[-1]
            spur = (deg[a] == 1 and deg[b] >= 3) or (deg[b] == 1 and deg[a] >= 3)
            if spur and len(path) < prune:
                continue
            kept.append(path)
        paths = kept
    return paths


def trace_centerline(
    mask: np.ndarray,
    epsilon: float = 1.0,
    min_length: int = 3,
    prune: int = 6,
) -> list[Polyline]:
    """
    Estrae la linea centrale delle forme.
    epsilon    : tolleranza di semplificazione (px)
    min_length : scarta tratti con meno di N pixel
    prune      : rimuove rami laterali più corti di N pixel (0 = disattivato)
    """
    padded = np.pad(mask, 1)
    skel = _skeletonize(padded)
    out: list[Polyline] = []
    for path in _skeleton_to_paths(skel, prune=prune):
        if len(path) < min_length:
            continue
        pts = np.array([(x, y) for y, x in path], dtype=np.float32) - 1.0
        closed = len(path) > 3 and path[0] == path[-1]
        if epsilon > 0:
            pts = cv2.approxPolyDP(pts.reshape(-1, 1, 2), epsilon, closed).reshape(-1, 2)
        if len(pts) >= 2:
            out.append(Polyline(pts.astype(float), closed))
    return out


# --------------------------------------------------------------------------
# API di alto livello
# --------------------------------------------------------------------------
def trace_image(
    path: str,
    mode: str = "outline",
    threshold: int | None = None,
    invert: bool = False,
    blur: int = 0,
    max_side: int | None = None,
    epsilon: float = 1.0,
    min_area: float = 4.0,
    min_length: int = 3,
    prune: int = 6,
) -> TraceResult:
    """mode: 'outline', 'centerline' oppure 'both'."""
    if mode not in ("outline", "centerline", "both"):
        raise ValueError("mode deve essere 'outline', 'centerline' o 'both'")
    mask = load_binary(path, threshold, invert, blur, max_side)
    h, w = mask.shape
    res = TraceResult(size=(w, h))
    if mode in ("outline", "both"):
        res.outlines = trace_outline(mask, epsilon, min_area)
    if mode in ("centerline", "both"):
        res.centerlines = trace_centerline(mask, epsilon, min_length, prune)
    return res


# --------------------------------------------------------------------------
# Esportazione SVG
# --------------------------------------------------------------------------
def _d(polylines: list[Polyline]) -> str:
    parts = []
    for pl in polylines:
        p = pl.points
        s = f"M{p[0][0]:.2f},{p[0][1]:.2f}" + "".join(
            f" L{x:.2f},{y:.2f}" for x, y in p[1:]
        )
        parts.append(s + (" Z" if pl.closed else ""))
    return " ".join(parts)


def save_svg(path: str, res: TraceResult, dpi: float | None = None) -> None:
    """
    Salva in SVG. Se dpi è indicato, width/height sono in millimetri
    (utile per importare nel software del laser alla scala corretta).
    """
    w, h = res.size
    if dpi:
        size = f'width="{w / dpi * 25.4:.3f}mm" height="{h / dpi * 25.4:.3f}mm" '
    else:
        size = f'width="{w}" height="{h}" '
    body = []
    if res.outlines:
        body.append(
            f'<path d="{_d(res.outlines)}" fill="none" stroke="#000" '
            f'stroke-width="1" vector-effect="non-scaling-stroke" id="outline"/>'
        )
    if res.centerlines:
        body.append(
            f'<path d="{_d(res.centerlines)}" fill="none" stroke="#f00" '
            f'stroke-width="1" vector-effect="non-scaling-stroke" id="centerline"/>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" {size}viewBox="0 0 {w} {h}">\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


# --------------------------------------------------------------------------
# Riga di comando
# --------------------------------------------------------------------------
def _main() -> None:
    ap = argparse.ArgumentParser(description="Traccia immagini in SVG")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--mode", choices=["outline", "centerline", "both"], default="outline")
    ap.add_argument("--threshold", type=int, default=None, help="soglia 0-255 (default Otsu)")
    ap.add_argument("--invert", action="store_true", help="primo piano = parte chiara")
    ap.add_argument("--blur", type=int, default=0)
    ap.add_argument("--max-side", type=int, default=None)
    ap.add_argument("--epsilon", type=float, default=1.0)
    ap.add_argument("--min-area", type=float, default=4.0)
    ap.add_argument("--min-length", type=int, default=3)
    ap.add_argument("--prune", type=int, default=6)
    ap.add_argument("--dpi", type=float, default=None)
    a = ap.parse_args()

    res = trace_image(
        a.input, a.mode, a.threshold, a.invert, a.blur, a.max_side,
        a.epsilon, a.min_area, a.min_length, a.prune,
    )
    save_svg(a.output, res, a.dpi)
    print(f"Contorni: {len(res.outlines)}  Linee centrali: {len(res.centerlines)}")


if __name__ == "__main__":
    _main()
