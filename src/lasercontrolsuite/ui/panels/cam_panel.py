"""Pannello CAM multi-layer (stile LightBurn).

Layout:
  - **Tabella layer** (in alto): una riga per layer, editabile in-place.
    Colonne: colore | nome | velocità | potenza | passate | air
  - **Opzioni globali**: S max, laser mode, travel feed, travel home,
    header comment.
  - **Azioni**: + Layer, − Rimuovi, ↑/↓ ordine, → Assegna selezione,
    genera, anteprima, invia.
  - **Statistiche**: riepilogo per layer + totale.

Interazioni:
  - **Click su una riga**: imposta il layer attivo e — se ci sono entità
    selezionate sul canvas — le assegna a quel layer (con undo, in un
    unico macro).
  - **Doppio click sulla cella del colore**: apre QColorDialog.
  - **Doppio click sulle altre celle**: le rende editabili in-place.
  - **Tasto destro su una riga**: menu contestuale.

Step 9d: ascolta `ThemeManager.themeChanged` per aggiornare la stylesheet
inline del widget `_stats`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lasercontrolsuite.cam import (
    GlobalParams,
    GCodeResult,
    LaserMode,
    build_preview,
    generate_gcode,
)
from lasercontrolsuite.config import Settings
from lasercontrolsuite.core.commands import ChangeEntityLayerCommand
from lasercontrolsuite.core.document import DocumentEvent
from lasercontrolsuite.core.layer import SUGGESTED_COLORS, Layer
from lasercontrolsuite.resources.theme import THEME
from lasercontrolsuite.resources.theme_manager import ThemeManager


class CamPanel(QWidget):
    """Pannello CAM con tabella layer editabile."""

    gcodeReady = Signal(str)

    COL_COLOR = 0
    COL_NAME = 1
    COL_SPEED = 2
    COL_POWER = 3
    COL_PASSES = 4
    COL_AIR = 5

    HEADERS = ("Colore", "Nome", "Velocità", "Potenza", "Passate", "Air")

    def __init__(self, canvas, parent=None, *, settings: Settings | None = None) -> None:
        super().__init__(parent)
        self._canvas = canvas
        self._settings = settings if settings is not None else Settings()
        self._last_gcode: str = ""
        self._last_stats_text: str = ""
        self._controller_available: bool = False
        self._updating_table: bool = False
        self._suppress_click_assign: bool = False

        self._build_ui()
        self._connect_signals()
        self._refresh_layer_table()
        self._refresh_send_enabled()

        ThemeManager.instance().themeChanged.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ API pubblica
    def current_global_params(self) -> GlobalParams:
        mode = self._laser_mode.currentData()
        return GlobalParams(
            travel_feed_mm_min=self._travel_feed.value(),
            s_max=self._s_max.value(),
            laser_mode=LaserMode(mode) if mode else LaserMode.M4,
            travel_home=self._travel_home.isChecked(),
            header_comment=self._header_comment.text(),
        )

    @property
    def last_gcode(self) -> str:
        return self._last_gcode

    @property
    def settings(self) -> Settings:
        return self._settings

    def set_controller_available(self, available: bool) -> None:
        self._controller_available = bool(available)
        self._refresh_send_enabled()

    # ------------------------------------------------------------------ tema
    def _on_theme_changed(self, _name: str) -> None:
        self._apply_stats_style()

    def _apply_stats_style(self) -> None:
        self._stats.setStyleSheet(
            f"color: {THEME.fg_secondary}; padding: 4px; "
            f"background: {THEME.bg_panel}; border-radius: 4px;"
        )

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        box_layers = QGroupBox("Layer di taglio (priority crescente)", self)
        v_layers = QVBoxLayout(box_layers)
        v_layers.setContentsMargins(4, 4, 4, 4)

        self._table = QTableWidget(0, len(self.HEADERS), box_layers)
        self._table.setHorizontalHeaderLabels(list(self.HEADERS))
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(self.COL_COLOR, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_SPEED, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_POWER, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_PASSES, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_AIR, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(self.COL_COLOR, 34)
        self._table.setToolTip(
            "Click su una riga: assegna le entità selezionate a questo layer.\n"
            "Doppio click sul colore: cambia colore.\n"
            "Doppio click sulle altre celle: modifica in-place."
        )
        v_layers.addWidget(self._table)

        row_layer = QHBoxLayout()
        self._btn_add_layer = QPushButton("+ Layer", self)
        self._btn_del_layer = QPushButton("− Rimuovi", self)
        self._btn_assign = QPushButton("→ Assegna selezione", self)
        self._btn_assign.setToolTip(
            "Assegna le entità selezionate sul canvas al layer selezionato"
        )
        self._btn_up = QToolButton(self)
        self._btn_up.setText("↑")
        self._btn_up.setToolTip("Sposta su il layer selezionato (priority −1)")
        self._btn_down = QToolButton(self)
        self._btn_down.setText("↓")
        self._btn_down.setToolTip("Sposta giù il layer selezionato (priority +1)")
        row_layer.addWidget(self._btn_add_layer)
        row_layer.addWidget(self._btn_del_layer)
        row_layer.addWidget(self._btn_assign)
        row_layer.addStretch(1)
        row_layer.addWidget(self._btn_up)
        row_layer.addWidget(self._btn_down)
        v_layers.addLayout(row_layer)
        root.addWidget(box_layers)

        box_gen = QGroupBox("Opzioni globali", self)
        form = QFormLayout(box_gen)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._travel_feed = QDoubleSpinBox(box_gen)
        self._travel_feed.setRange(0.0, 30000.0)
        self._travel_feed.setDecimals(0)
        self._travel_feed.setSuffix(" mm/min")
        self._travel_feed.setSpecialValueText("default")
        form.addRow("Rapido (0 = default):", self._travel_feed)

        self._s_max = QSpinBox(box_gen)
        self._s_max.setRange(1, 100000)
        self._s_max.setValue(1000)
        form.addRow("S max ($30):", self._s_max)

        self._laser_mode = QComboBox(box_gen)
        self._laser_mode.addItem("M4 (dinamico)", LaserMode.M4.value)
        self._laser_mode.addItem("M3 (costante)", LaserMode.M3.value)
        form.addRow("Modalità laser:", self._laser_mode)

        self._travel_home = QCheckBox("Torna all'origine a fine lavoro", box_gen)
        self._travel_home.setChecked(True)
        form.addRow("", self._travel_home)

        self._header_comment = QLineEdit(box_gen)
        self._header_comment.setPlaceholderText("(opzionale) commento di testa")
        form.addRow("Commento:", self._header_comment)

        self._optimize = QCheckBox("Ottimizza ordine percorsi per layer", box_gen)
        self._optimize.setChecked(True)
        form.addRow("", self._optimize)

        self._only_selected = QCheckBox("Solo entità selezionate", box_gen)
        form.addRow("", self._only_selected)

        root.addWidget(box_gen)

        actions = QHBoxLayout()
        self._btn_generate = QPushButton("Genera G-code", self)
        self._btn_preview = QPushButton("Anteprima…", self)
        self._btn_send = QPushButton("Invia al controller", self)
        self._btn_send.setEnabled(False)
        actions.addWidget(self._btn_generate)
        actions.addWidget(self._btn_preview)
        actions.addWidget(self._btn_send)
        root.addLayout(actions)

        self._stats = QLabel("—", self)
        self._stats.setWordWrap(True)
        self._apply_stats_style()
        root.addWidget(self._stats)

        self._preview = QPlainTextEdit(self)
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("Anteprima G-code (prime righe)")
        self._preview.setMaximumHeight(180)
        root.addWidget(self._preview, 1)

    # ------------------------------------------------------------------ segnali
    def _connect_signals(self) -> None:
        self._btn_generate.clicked.connect(self._on_generate)
        self._btn_preview.clicked.connect(self._on_preview)
        self._btn_send.clicked.connect(self._on_send)
        self._btn_add_layer.clicked.connect(self._on_add_layer)
        self._btn_del_layer.clicked.connect(self._on_remove_layer)
        self._btn_assign.clicked.connect(self._on_assign_selection)
        self._btn_up.clicked.connect(lambda: self._move_layer(-1))
        self._btn_down.clicked.connect(lambda: self._move_layer(+1))

        self._table.itemChanged.connect(self._on_table_item_changed)
        self._table.cellClicked.connect(self._on_table_cell_clicked)
        self._table.itemDoubleClicked.connect(self._on_table_item_double_clicked)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

        doc = self._document()
        if doc is not None:
            doc.subscribe(self._on_document_event)

    # ------------------------------------------------------------------ helpers
    def _document(self):
        try:
            return self._canvas.cad_scene.document
        except AttributeError:
            return None

    def _selected_entity_ids(self) -> list[str]:
        try:
            items = self._canvas.cad_scene.selectedItems()
        except Exception:
            return []
        from lasercontrolsuite.cad.entity_item import EntityItem

        return [
            item.entity.id for item in items if isinstance(item, EntityItem)
        ]

    def _refresh_layer_table(self) -> None:
        doc = self._document()
        if doc is None:
            return
        prev_block = self._table.blockSignals(True)
        self._updating_table = True
        try:
            layers = list(doc.layers.values())
            layers_sorted = sorted(
                layers,
                key=lambda l: (l.priority, list(doc.layers.keys()).index(l.id)),
            )
            self._table.setRowCount(len(layers_sorted))
            for row, layer in enumerate(layers_sorted):
                self._populate_row(row, layer)
        finally:
            self._updating_table = False
            self._table.blockSignals(prev_block)

    def _populate_row(self, row: int, layer: Layer) -> None:
        color_item = QTableWidgetItem()
        color_item.setBackground(QColor(layer.color))
        color_item.setToolTip(f"{layer.color} — doppio click per cambiare")
        color_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self._table.setItem(row, self.COL_COLOR, color_item)

        name_item = QTableWidgetItem(layer.name)
        name_item.setData(Qt.ItemDataRole.UserRole, layer.id)
        self._table.setItem(row, self.COL_NAME, name_item)

        speed_item = QTableWidgetItem(f"{layer.speed_mm_min:.0f}")
        speed_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._table.setItem(row, self.COL_SPEED, speed_item)

        power_item = QTableWidgetItem(f"{layer.power_percent}")
        power_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._table.setItem(row, self.COL_POWER, power_item)

        passes_item = QTableWidgetItem(f"{layer.passes}")
        passes_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._table.setItem(row, self.COL_PASSES, passes_item)

        air_item = QTableWidgetItem()
        air_item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsSelectable
        )
        air_item.setCheckState(
            Qt.CheckState.Checked if layer.air_assist else Qt.CheckState.Unchecked
        )
        self._table.setItem(row, self.COL_AIR, air_item)

    def _find_row_for_layer(self, layer_id: str) -> int:
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, self.COL_NAME)
            if name_item is None:
                continue
            if name_item.data(Qt.ItemDataRole.UserRole) == layer_id:
                return row
        return -1

    def _update_layer_row(self, layer_id: str) -> None:
        doc = self._document()
        if doc is None:
            return
        layer = doc.get_layer(layer_id)
        if layer is None:
            return
        row = self._find_row_for_layer(layer_id)
        if row < 0:
            return

        prev_block = self._table.blockSignals(True)
        self._updating_table = True
        try:
            color_item = self._table.item(row, self.COL_COLOR)
            if color_item is not None:
                color_item.setBackground(QColor(layer.color))
                color_item.setToolTip(f"{layer.color} — doppio click per cambiare")

            name_item = self._table.item(row, self.COL_NAME)
            if name_item is not None and name_item.text() != layer.name:
                name_item.setText(layer.name)

            speed_item = self._table.item(row, self.COL_SPEED)
            if speed_item is not None:
                txt = f"{layer.speed_mm_min:.0f}"
                if speed_item.text() != txt:
                    speed_item.setText(txt)

            power_item = self._table.item(row, self.COL_POWER)
            if power_item is not None:
                txt = f"{layer.power_percent}"
                if power_item.text() != txt:
                    power_item.setText(txt)

            passes_item = self._table.item(row, self.COL_PASSES)
            if passes_item is not None:
                txt = f"{layer.passes}"
                if passes_item.text() != txt:
                    passes_item.setText(txt)

            air_item = self._table.item(row, self.COL_AIR)
            if air_item is not None:
                want = (
                    Qt.CheckState.Checked
                    if layer.air_assist
                    else Qt.CheckState.Unchecked
                )
                if air_item.checkState() != want:
                    air_item.setCheckState(want)
        finally:
            self._updating_table = False
            self._table.blockSignals(prev_block)

    # ------------------------------------------------------------------ assegnazione
    def _assign_entities_to_layer(self, layer_id: str, entity_ids: list[str]) -> int:
        doc = self._document()
        if doc is None:
            return 0
        to_move: list[str] = []
        for eid in entity_ids:
            e = doc.get_entity(eid)
            if e is not None and e.layer_id != layer_id:
                to_move.append(eid)
        if not to_move:
            return 0

        scene = self._canvas.cad_scene
        stack = scene.undo_stack
        layer = doc.get_layer(layer_id)
        layer_name = layer.name if layer is not None else layer_id
        stack.beginMacro(f"Assegna {len(to_move)} entità a {layer_name}")
        try:
            for eid in to_move:
                stack.push(ChangeEntityLayerCommand(doc, eid, layer_id))
        finally:
            stack.endMacro()

        if layer is not None:
            for eid in to_move:
                item = scene.entity_item(eid)
                if item is not None:
                    item.sync_from_layer(layer)

        return len(to_move)

    # ------------------------------------------------------------------ slots: tabella
    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table:
            return
        doc = self._document()
        if doc is None:
            return

        try:
            row = item.row()
        except RuntimeError:
            return

        name_item = self._table.item(row, self.COL_NAME)
        if name_item is None:
            return
        layer_id = name_item.data(Qt.ItemDataRole.UserRole)
        layer = doc.get_layer(layer_id) if layer_id else None
        if layer is None:
            return

        col = item.column()
        self._updating_table = True
        try:
            if col == self.COL_NAME:
                new_name = item.text().strip() or layer.name
                layer.name = new_name
                if item.text() != new_name:
                    item.setText(new_name)
            elif col == self.COL_SPEED:
                try:
                    v = float(item.text().replace(",", "."))
                except ValueError:
                    v = layer.speed_mm_min
                v = max(1.0, v)
                layer.speed_mm_min = v
                item.setText(f"{v:.0f}")
            elif col == self.COL_POWER:
                try:
                    v = int(round(float(item.text())))
                except ValueError:
                    v = layer.power_percent
                v = max(0, min(100, v))
                layer.power_percent = v
                item.setText(f"{v}")
            elif col == self.COL_PASSES:
                try:
                    v = int(item.text())
                except ValueError:
                    v = layer.passes
                v = max(1, v)
                layer.passes = v
                item.setText(f"{v}")
            elif col == self.COL_AIR:
                checked = item.checkState() == Qt.CheckState.Checked
                layer.air_assist = checked
        finally:
            self._updating_table = False

    def _on_table_cell_clicked(self, row: int, col: int) -> None:
        if self._updating_table or self._suppress_click_assign:
            return
        doc = self._document()
        if doc is None:
            return
        name_item = self._table.item(row, self.COL_NAME)
        if name_item is None:
            return
        layer_id = name_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(layer_id, str):
            return

        if doc.active_layer_id != layer_id:
            doc.set_active_layer(layer_id)

        sel_ids = self._selected_entity_ids()
        if not sel_ids:
            return
        n = self._assign_entities_to_layer(layer_id, sel_ids)
        if n > 0:
            self._stats.setText(
                f"{n} entità assegnate a '{name_item.text()}'."
            )

    def _on_table_item_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.column() == self.COL_COLOR:
            self._suppress_click_assign = True
            try:
                self._edit_layer_color(item.row())
            finally:
                self._suppress_click_assign = False

    def _edit_layer_color(self, row: int) -> None:
        doc = self._document()
        if doc is None:
            return
        name_item = self._table.item(row, self.COL_NAME)
        if name_item is None:
            return
        lid = name_item.data(Qt.ItemDataRole.UserRole)
        layer = doc.get_layer(lid) if isinstance(lid, str) else None
        if layer is None:
            return
        initial = QColor(layer.color) if layer.color else QColor("#FFD400")
        color = QColorDialog.getColor(initial, self, "Colore layer")
        if not color.isValid():
            return
        layer.color = color.name()
        doc._emit(DocumentEvent("layer_changed", layer_id=layer.id))

    def _on_table_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        name_item = self._table.item(row, self.COL_NAME)
        if name_item is None:
            return
        layer_name = name_item.text()

        menu = QMenu(self)
        act_assign = QAction(f"Assegna selezione a '{layer_name}'", self)
        act_color = QAction("Cambia colore…", self)
        act_rename = QAction("Rinomina…", self)
        menu.addAction(act_assign)
        menu.addSeparator()
        menu.addAction(act_color)
        menu.addAction(act_rename)

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act_assign:
            self._on_assign_selection()
        elif chosen is act_color:
            self._suppress_click_assign = True
            try:
                self._edit_layer_color(row)
            finally:
                self._suppress_click_assign = False
        elif chosen is act_rename:
            self._suppress_click_assign = True
            try:
                self._table.editItem(name_item)
            finally:
                self._suppress_click_assign = False

    # ------------------------------------------------------------------ slots: layer
    def _selected_layer_id(self) -> str | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        name_item = self._table.item(row, self.COL_NAME)
        if name_item is None:
            return None
        lid = name_item.data(Qt.ItemDataRole.UserRole)
        return lid if isinstance(lid, str) else None

    def _on_add_layer(self) -> None:
        doc = self._document()
        if doc is None:
            return
        existing = list(doc.layers.values())
        next_prio = (max((l.priority for l in existing), default=-1)) + 1
        color = SUGGESTED_COLORS[len(existing) % len(SUGGESTED_COLORS)]
        name = f"Layer {len(existing) + 1}"
        layer = Layer.new(name=name, color=color, priority=next_prio)
        doc.add_layer(layer)

    def _on_remove_layer(self) -> None:
        doc = self._document()
        if doc is None:
            return
        lid = self._selected_layer_id()
        if lid is None:
            return
        if len(doc.layers) <= 1:
            self._stats.setText("Non puoi rimuovere l'ultimo layer.")
            return
        doc.remove_layer(lid)

    def _move_layer(self, delta: int) -> None:
        doc = self._document()
        if doc is None:
            return
        lid = self._selected_layer_id()
        if lid is None:
            return
        layer = doc.get_layer(lid)
        if layer is None:
            return
        layer.priority = max(0, layer.priority + delta)
        doc._emit(DocumentEvent("layer_changed", layer_id=layer.id))
        self._refresh_layer_table()

    def _on_assign_selection(self) -> None:
        lid = self._selected_layer_id()
        if lid is None:
            self._stats.setText("Seleziona un layer in tabella.")
            return
        sel_ids = self._selected_entity_ids()
        if not sel_ids:
            self._stats.setText("Nessuna entità selezionata sul canvas.")
            return
        n = self._assign_entities_to_layer(lid, sel_ids)
        if n == 0:
            self._stats.setText("Le entità selezionate sono già su questo layer.")
            return
        doc = self._document()
        layer = doc.get_layer(lid) if doc is not None else None
        name = layer.name if layer is not None else "?"
        self._stats.setText(f"{n} entità assegnate a '{name}'.")

    # ------------------------------------------------------------------ slots: doc
    def _on_document_event(self, event: DocumentEvent) -> None:
        if self._updating_table:
            return
        if event.type in ("layer_added", "layer_removed"):
            self._refresh_layer_table()
        elif event.type == "layer_changed" and event.layer_id:
            self._update_layer_row(event.layer_id)

    # ------------------------------------------------------------------ generazione
    def _selected_ids(self) -> set[str] | None:
        if not self._only_selected.isChecked():
            return None
        ids = set(self._selected_entity_ids())
        return ids if ids else set()

    def _generate_result(self) -> GCodeResult | None:
        doc = self._document()
        if doc is None:
            return None
        only = self._selected_ids()
        if only is not None and not only:
            self._stats.setText("Nessuna entità selezionata.")
            return None
        try:
            result = generate_gcode(
                doc,
                self.current_global_params(),
                optimize=self._optimize.isChecked(),
                only_selected_ids=only,
            )
        except Exception as exc:  # noqa: BLE001
            self._stats.setText(f"Errore: {exc}")
            return None

        self._last_gcode = result.gcode
        st = result.stats
        lines = [
            f"Layer: {len(result.layer_stats)} — "
            f"Percorsi: {st.n_paths} — Passate: {st.n_passes} — "
            f"Lunghezza taglio: {st.cut_length_mm:.1f} mm — "
            f"Tempo stimato: {st.estimated_total_time_str()}",
        ]
        for ls in result.layer_stats:
            lines.append(
                f"  • {ls.layer_name}: {ls.n_paths} perc, "
                f"{ls.cut_length_mm:.1f} mm, {ls.estimated_cut_time_str()}, "
                f"S{ls.s_value} @ F{ls.feed_mm_min:.0f}"
            )
        self._last_stats_text = "\n".join(lines)
        self._stats.setText(self._last_stats_text)

        head_lines = self._last_gcode.splitlines()[:40]
        self._preview.setPlainText("\n".join(head_lines))
        return result

    def _on_generate(self) -> bool:
        result = self._generate_result()
        return bool(result and result.gcode.strip())

    def _on_preview(self) -> None:
        result = self._generate_result()
        if result is None:
            return
        preview_scene = build_preview(result.paths, include_travel=True)
        machine = self._settings.get_active_machine()

        from lasercontrolsuite.ui.dialogs.gcode_viewer_dialog import GCodeViewerDialog

        dlg = GCodeViewerDialog(
            self._last_gcode,
            self._last_stats_text,
            preview_scene=preview_scene,
            machine=machine,
            parent=self.window(),
        )
        dlg.exec()

    def _on_send(self) -> None:
        if not self._controller_available:
            self._stats.setText("Controller non connesso.")
            return
        if not self._on_generate():
            return
        self.gcodeReady.emit(self._last_gcode)

    # ------------------------------------------------------------------ helpers UI
    def _refresh_send_enabled(self) -> None:
        self._btn_send.setEnabled(self._controller_available)