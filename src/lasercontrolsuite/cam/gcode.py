"""Generazione G-code dal documento (multi-layer).

Step 9c — Multi-layer
---------------------
I percorsi vengono raggruppati per layer e lavorati in sequenza secondo la
``priority`` del layer (crescente). Per ogni layer si emette un blocco con:

    ; ---- Layer <name> (priority N) ----
    ; Feed: F mm/min — Power: P% — S: 0..s_max — Mode: M4 — Passes: K
    [M8]                         ; air assist ON (se attivo)
    <percorsi del layer>
    [M9]                         ; air assist OFF (se attivo)

L'header e il footer del programma (G21/G90/G94, laser off, ritorno a home)
restano globali.

Compatibilità
-------------
``generate_gcode`` accetta:
  - ``params=None``            → usa layer + GlobalParams() di default
  - ``params=GlobalParams()``  → usa layer + globali specificati
  - ``params=CutParams()``     → **legacy**: un unico set di parametri
                                 applicato a tutti i layer (comportamento
                                 pre-9c, utile per i test).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lasercontrolsuite.cam.flatten import FlatPath, flatten_document
from lasercontrolsuite.cam.layer_stats import LayerCutStats, compute_layer_stats
from lasercontrolsuite.cam.order import order_paths
from lasercontrolsuite.cam.params import CutParams, GlobalParams, LaserMode
from lasercontrolsuite.cam.stats import GCodeStats, estimate_stats


@dataclass
class GCodeResult:
    """Risultato completo della generazione G-code."""

    gcode: str
    paths: list[FlatPath] = field(default_factory=list)
    stats: GCodeStats = field(default_factory=GCodeStats)
    layer_stats: list[LayerCutStats] = field(default_factory=list)


# =====================================================================
# API principale
# =====================================================================
def generate_gcode(
    document,
    params: CutParams | GlobalParams | None = None,
    *,
    optimize: bool = True,
    only_selected_ids: set[str] | None = None,
) -> GCodeResult:
    """Genera G-code dalle entità visibili del documento.

    Args:
        document: ``Document`` del core.
        params:
            - ``None`` → multi-layer, globali di default.
            - ``GlobalParams`` → multi-layer, globali specificati.
            - ``CutParams`` → legacy: un unico set di parametri per tutto.
        optimize: applica l'ordinamento nearest-neighbor per layer.
        only_selected_ids: se valorizzato, considera solo le entità con
            questi id.
    """
    legacy_cut: CutParams | None = None
    global_params: GlobalParams
    if isinstance(params, CutParams):
        legacy_cut = params.normalized()
        global_params = GlobalParams(
            travel_feed_mm_min=legacy_cut.travel_feed_mm_min,
            s_max=legacy_cut.s_max,
            laser_mode=legacy_cut.laser_mode,
            travel_home=legacy_cut.travel_home,
            header_comment=legacy_cut.header_comment,
        )
    elif isinstance(params, GlobalParams):
        global_params = params.normalized()
    else:
        global_params = GlobalParams()

    all_paths = flatten_document(document)
    if only_selected_ids is not None:
        all_paths = [fp for fp in all_paths if fp.entity_id in only_selected_ids]

    if not all_paths:
        return GCodeResult(
            gcode=_empty_program(global_params, legacy_cut),
            paths=[],
            stats=GCodeStats(),
            layer_stats=[],
        )

    # Raggruppa per layer rispettando l'ordine di priority, poi di inserimento.
    grouped, layer_order = _group_by_layer(all_paths, document)
    # Filtra i layer che non hanno percorsi
    layer_order = [lid for lid in layer_order if grouped.get(lid)]

    # Per ogni layer: parametri, ordinamento interno, statistiche.
    ordered_all: list[FlatPath] = []
    layer_stats: list[LayerCutStats] = []
    layer_blocks: list[tuple] = []   # (layer, paths_ordered, cut_params, stats)

    for lid in layer_order:
        paths = grouped[lid]
        layer = document.get_layer(lid)

        if legacy_cut is not None:
            cut = legacy_cut
        elif layer is not None:
            cut = CutParams.from_layer(layer, global_params)
        else:
            cut = CutParams.from_layer(
                _fallback_layer(lid), global_params
            )

        ordered = order_paths(paths) if optimize else list(paths)
        stats = compute_layer_stats(ordered, cut)

        ordered_all.extend(ordered)
        layer_stats.append(stats)
        layer_blocks.append((layer, ordered, cut, stats))

    # Emissione del G-code.
    lines: list[str] = []
    _emit_header(
        lines,
        global_params,
        n_entities=len({fp.entity_id for fp in ordered_all}),
        n_paths=len(ordered_all),
        n_layers=len(layer_blocks),
    )
    _emit_program(lines, layer_blocks, global_params)
    _emit_footer(lines, global_params)

    gcode = "\n".join(lines) + "\n"
    stats_total = estimate_stats(ordered_all, _aggregate_params(layer_blocks, global_params),
                                 gcode_line_count=len(lines))
    # Sovrascrive i campi più informativi con i totali per-layer
    stats_total.n_paths = sum(s.n_paths for s in layer_stats)
    stats_total.n_passes = sum(s.n_passes for s in layer_stats)
    stats_total.cut_length_mm = sum(s.cut_length_mm for s in layer_stats)
    stats_total.estimated_cut_seconds = sum(s.estimated_cut_seconds for s in layer_stats)

    return GCodeResult(
        gcode=gcode,
        paths=ordered_all,
        stats=stats_total,
        layer_stats=layer_stats,
    )


# =====================================================================
# Raggruppamento per layer
# =====================================================================
def _group_by_layer(paths: list[FlatPath], document):
    """Ritorna (gruppi_per_layer, ordine_layer).

    L'ordine dei layer rispetta la ``priority`` crescente; a parità di
    priority, l'ordine di inserimento nel documento (dict insertion order).
    I layer senza priority definita ma presenti nel documento vengono
    inclusi.
    """
    grouped: dict[str, list[FlatPath]] = {}
    for p in paths:
        grouped.setdefault(p.layer_id, []).append(p)

    # Ordina i layer per priority (crescente) preservando l'ordine di
    # inserimento nel documento per i pareggi.
    def sort_key(lid: str) -> tuple[int, int]:
        layer = document.get_layer(lid)
        prio = layer.priority if layer is not None else 0
        try:
            insertion = list(document.layers.keys()).index(lid)
        except ValueError:
            insertion = len(document.layers)
        return (prio, insertion)

    order = sorted(grouped.keys(), key=sort_key)
    return grouped, order


def _fallback_layer(layer_id: str):
    """Layer placeholder per ``layer_id`` orfani (entità rimaste senza layer)."""
    from lasercontrolsuite.core.layer import Layer

    return Layer(id=layer_id, name="(orfano)")


def _aggregate_params(
    layer_blocks: list[tuple], global_params: GlobalParams
) -> CutParams:
    """CutParams "riassuntivi" per il calcolo delle stats globali."""
    if not layer_blocks:
        return CutParams.from_layer(_fallback_layer(""), global_params)
    # Usa il primo layer come riferimento; le stats per-layer sono aggregate
    # separatamente sopra.
    _, _, cut, _ = layer_blocks[0]
    return cut


# =====================================================================
# Emissione
# =====================================================================
def _emit_header(
    lines: list[str],
    g: GlobalParams,
    n_entities: int,
    n_paths: int,
    n_layers: int,
) -> None:
    lines.append("; LaserControlSuite — G-code generato automaticamente")
    if g.header_comment:
        for ln in str(g.header_comment).splitlines():
            lines.append(f"; {ln}")
    lines.append(
        f"; Entità: {n_entities}, Percorsi: {n_paths}, Layer: {n_layers}"
    )
    lines.append(
        f"; S max: {g.s_max} — Mode: {g.laser_mode.value}"
    )
    if g.laser_mode is LaserMode.M4:
        lines.append("; M4 richiede $32=1 (laser mode) sul controller")
    lines.append(";")
    lines.append("G21         ; millimetri")
    lines.append("G90         ; coordinate assolute")
    lines.append("G94         ; feed per minuto")
    lines.append("M5          ; laser off (sicurezza)")
    lines.append("")


def _emit_footer(lines: list[str], g: GlobalParams) -> None:
    lines.append("M5          ; laser off (fine programma)")
    if g.travel_home:
        lines.append("G0 X0.000 Y0.000  ; ritorno all'origine")
    lines.append("; Fine")


def _emit_program(
    lines: list[str],
    layer_blocks: list[tuple],
    g: GlobalParams,
) -> None:
    for idx, (layer, paths, cut, stats) in enumerate(layer_blocks, start=1):
        name = layer.name if layer is not None else f"layer {cut.layer_id[:8]}"
        prio = layer.priority if layer is not None else 0
        lines.append(
            f"; ===================== Layer {idx}: {name} "
            f"(priority {prio}) ====================="
        )
        lines.append(
            f"; Feed: {cut.feed_mm_min:.0f} mm/min — Power: "
            f"{cut.power_percent:.0f}% — S: {cut.s_value()} — "
            f"Mode: {cut.laser_mode.value} — Passes: {cut.passes} — "
            f"Air: {'ON' if cut.air_assist else 'OFF'}"
        )
        if cut.air_assist:
            lines.append("M8          ; air assist ON")
        lines.append("")

        _emit_layer_paths(lines, paths, cut)

        if cut.air_assist:
            lines.append("M9          ; air assist OFF")
        lines.append("")


def _emit_layer_paths(
    lines: list[str],
    paths: list[FlatPath],
    cut: CutParams,
) -> None:
    s = cut.s_value()
    feed = cut.feed_mm_min
    total_paths = len(paths)

    for pass_i in range(cut.passes):
        if cut.passes > 1:
            lines.append(f"; ---- Passata {pass_i + 1}/{cut.passes} ----")
            lines.append("")

        for path_i, path in enumerate(paths, start=1):
            lines.append(f"; Percorso {path_i}/{total_paths}")

            x0, y0 = path.points[0]
            lines.append(f"G0 X{x0:.3f} Y{y0:.3f}")

            lines.append(f"{cut.laser_mode.value} S{s}")
            first = True
            for (x, y) in path.points[1:]:
                if first:
                    lines.append(f"G1 X{x:.3f} Y{y:.3f} F{feed:.0f}")
                    first = False
                else:
                    lines.append(f"G1 X{x:.3f} Y{y:.3f}")

            if path.closed and len(path.points) >= 2:
                lines.append(f"G1 X{x0:.3f} Y{y0:.3f}")

            lines.append("M5")
            lines.append("")


def _empty_program(g: GlobalParams, legacy_cut: CutParams | None) -> str:
    lines: list[str] = []
    _emit_header(lines, g, n_entities=0, n_paths=0, n_layers=0)
    lines.append("; Nessuna entità da lavorare")
    _emit_footer(lines, g)
    return "\n".join(lines) + "\n"