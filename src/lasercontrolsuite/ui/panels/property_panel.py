"""Pannello proprietà dockable con binding bidirezionale sul documento.

Robustezza:
  - Le callback dei segnali Qt e dell'observer del documento possono essere
    invocate *dopo* che il C++ sottostante è stato distrutto (chiusura app,
    distruzione della scena). Per questo ogni callback fa un check tramite
    ``shiboken6.isValid()`` prima di accedere ai wrapper Qt.
  - Nel ``closeEvent`` (e via ``detach()``) ci disconnettiamo esplicitamente
    da tutti i segnali e ci cancelliamo dall'observer del documento, così non
    riceviamo più nulla dopo la chiusura.
  - ``detach()`` è **totalmente difensivo**: non assume che ``self._scene``
    sia una scena Qt valida. Regge scenari limite (mock, oggetti parziali,
    wrapper con C++ morto).
"""

from __future__ import annotations

import math

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lasercontrolsuite.cad.entity_item import EntityItem
from lasercontrolsuite.core.commands import (
    ChangeEntityLayerCommand,
    TransformEntityCommand,
)
from lasercontrolsuite.core.document import DocumentEvent
from lasercontrolsuite.core.entities import Entity
from lasercontrolsuite.core.layer import Layer
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.operations import rotation_of


class PropertyPanel(QDockWidget):
    """Dock di destra con le proprietà della selezione."""

    def __init__(self, canvas, parent=None) -> None:
        super().__init__("Proprietà", parent)
        self.setObjectName("PropertyPanel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )

        self._canvas = canvas
        self._scene = canvas.cad_scene
        self._document = self._scene.document
        self._updating = False
        self._detached = False

        self._build_ui()
        self._connect_signals()
        self._refresh()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self._type_label = QLabel("—", root)
        self._type_label.setStyleSheet("font-weight: bold;")
        outer.addWidget(self._type_label)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setSpacing(6)

        self._x = self._make_spin(-1e6, 1e6)
        self._y = self._make_spin(-1e6, 1e6)
        self._w = self._make_spin(0.001, 1e6)
        self._h = self._make_spin(0.001, 1e6)
        self._r = self._make_spin(-360.0, 360.0, decimals=2)

        self._layer = QComboBox(root)
        for layer in self._document.layers.values():
            self._add_layer_item(layer)

        form.addRow("X (mm):", self._x)
        form.addRow("Y (mm):", self._y)
        form.addRow("Larghezza (mm):", self._w)
        form.addRow("Altezza (mm):", self._h)
        form.addRow("Rotazione (°):", self._r)
        form.addRow("Layer:", self._layer)
        outer.addLayout(form)

        outer.addStretch(1)

        self._apply_layer_btn = QPushButton("Applica layer", root)
        outer.addWidget(self._apply_layer_btn)

    def _make_spin(self, lo: float, hi: float, decimals: int = 3) -> QDoubleSpinBox:
        box = QDoubleSpinBox(self)
        box.setDecimals(decimals)
        box.setRange(lo, hi)
        box.setSingleStep(1.0 if decimals <= 3 else 0.1)
        box.setKeyboardTracking(False)
        return box

    def _add_layer_item(self, layer: Layer) -> None:
        self._layer.addItem(layer.name, layer.id)

    def _connect_signals(self) -> None:
        self._scene.selectionChanged.connect(self._refresh)
        self._document.subscribe(self._on_document_event)

        self._x.editingFinished.connect(self._on_x_changed)
        self._y.editingFinished.connect(self._on_y_changed)
        self._w.editingFinished.connect(self._on_w_changed)
        self._h.editingFinished.connect(self._on_h_changed)
        self._r.editingFinished.connect(self._on_r_changed)
        self._apply_layer_btn.clicked.connect(self._on_apply_layer)

    # --------------------------------------------------------------- lifecycle
    def detach(self) -> None:
        """Disconnette segnali e observer. Idempotente e totalmente difensivo.

        Non assume che ``self._scene`` sia una scena Qt valida: gestisce
        scenari limite (mock, oggetti parziali, wrapper con C++ morto).
        """
        if self._detached:
            return
        self._detached = True

        # Disconnessione dal segnale di selezione (se possibile)
        if self._scene is not None and shiboken6.isValid(self._scene):
            try:
                if hasattr(self._scene, "selectionChanged"):
                    self._scene.selectionChanged.disconnect(self._refresh)
            except (RuntimeError, AttributeError, TypeError):
                # C++ distrutto, attributo assente, firma incompatibile:
                # in tutti i casi, non c'è nulla da disconnettere.
                pass

        # Cancellazione dall'observer del documento
        if self._document is not None:
            try:
                self._document.unsubscribe(self._on_document_event)
            except (RuntimeError, AttributeError, TypeError):
                pass

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.detach()
        super().closeEvent(event)

    # --------------------------------------------------------------- safety
    def _is_scene_alive(self) -> bool:
        """True se possiamo accedere in sicurezza ai metodi della scena."""
        if self._detached:
            return False
        if self._scene is None:
            return False
        try:
            return shiboken6.isValid(self._scene)
        except (RuntimeError, TypeError):
            return False

    def _selected_entities(self) -> list[Entity]:
        """Entità selezionate. Ritorna [] se la scena non è più valida."""
        if not self._is_scene_alive():
            return []
        try:
            items = self._scene.selectedItems()
        except (RuntimeError, AttributeError):
            return []
        return [item.entity for item in items if isinstance(item, EntityItem)]

    # --------------------------------------------------------------- observers
    def _on_document_event(self, event: DocumentEvent) -> None:
        if not self._is_scene_alive():
            return
        ids = {e.id for e in self._selected_entities()}
        if event.entity_id is not None and event.entity_id in ids:
            self._refresh()
        elif event.type == "layer_added" and event.layer_id is not None:
            layer = self._document.get_layer(event.layer_id)
            if layer is not None and self._layer.findData(layer.id) < 0:
                self._add_layer_item(layer)
        elif event.type == "layer_removed" and event.layer_id is not None:
            idx = self._layer.findData(event.layer_id)
            if idx >= 0:
                self._layer.removeItem(idx)

    def _refresh(self) -> None:
        if self._updating:
            return
        if not self._is_scene_alive():
            return

        self._updating = True
        try:
            selected = self._selected_entities()
            if len(selected) == 1:
                e = selected[0]
                self._type_label.setText(type(e).__name__)
                x0, y0, x1, y1 = e.world_bounding_box()
                self._set_value(self._x, x0)
                self._set_value(self._y, y0)
                self._set_value(self._w, max(1e-6, x1 - x0))
                self._set_value(self._h, max(1e-6, y1 - y0))
                angle_deg = math.degrees(rotation_of(e.transform))
                self._set_value(self._r, angle_deg)
                idx = self._layer.findData(e.layer_id)
                if idx >= 0:
                    self._layer.setCurrentIndex(idx)
                self._set_enabled(True)
            elif len(selected) == 0:
                self._type_label.setText("—")
                self._set_enabled(False)
            else:
                self._type_label.setText(f"{len(selected)} entità")
                self._set_enabled(False)
        finally:
            self._updating = False

    def _set_value(self, box: QDoubleSpinBox, v: float) -> None:
        blocked = box.blockSignals(True)
        try:
            box.setValue(v)
        finally:
            box.blockSignals(blocked)

    def _set_enabled(self, enabled: bool) -> None:
        for w in (
            self._x, self._y, self._w, self._h, self._r,
            self._layer, self._apply_layer_btn,
        ):
            w.setEnabled(enabled)

    # --------------------------------------------------------------- editing
    def _single_selected(self) -> Entity | None:
        selected = self._selected_entities()
        return selected[0] if len(selected) == 1 else None

    def _push_transform(self, entity: Entity, new_transform: Matrix2D, label: str) -> None:
        cmd = TransformEntityCommand(self._document, entity.id, new_transform)
        cmd.setText(label)
        self._scene.undo_stack.push(cmd)

    def _on_x_changed(self) -> None:
        if self._updating:
            return
        e = self._single_selected()
        if e is None:
            return
        x0, _, _, _ = e.world_bounding_box()
        dx = self._x.value() - x0
        if abs(dx) < 1e-9:
            return
        self._push_transform(e, Matrix2D.translation(dx, 0.0) @ e.transform, "Sposta X")

    def _on_y_changed(self) -> None:
        if self._updating:
            return
        e = self._single_selected()
        if e is None:
            return
        _, y0, _, _ = e.world_bounding_box()
        dy = self._y.value() - y0
        if abs(dy) < 1e-9:
            return
        self._push_transform(e, Matrix2D.translation(0.0, dy) @ e.transform, "Sposta Y")

    def _on_w_changed(self) -> None:
        if self._updating:
            return
        e = self._single_selected()
        if e is None:
            return
        x0, _, x1, _ = e.world_bounding_box()
        cur = x1 - x0
        new = self._w.value()
        if cur < 1e-9 or abs(new - cur) < 1e-9:
            return
        s = new / cur
        cx = (x0 + x1) / 2.0
        scale = Matrix2D.scaling(s, 1.0)
        new_t = (
            Matrix2D.translation(cx, 0.0)
            @ scale
            @ Matrix2D.translation(-cx, 0.0)
            @ e.transform
        )
        self._push_transform(e, new_t, "Scala larghezza")

    def _on_h_changed(self) -> None:
        if self._updating:
            return
        e = self._single_selected()
        if e is None:
            return
        _, y0, _, y1 = e.world_bounding_box()
        cur = y1 - y0
        new = self._h.value()
        if cur < 1e-9 or abs(new - cur) < 1e-9:
            return
        s = new / cur
        cy = (y0 + y1) / 2.0
        scale = Matrix2D.scaling(1.0, s)
        new_t = (
            Matrix2D.translation(0.0, cy)
            @ scale
            @ Matrix2D.translation(0.0, -cy)
            @ e.transform
        )
        self._push_transform(e, new_t, "Scala altezza")

    def _on_r_changed(self) -> None:
        if self._updating:
            return
        e = self._single_selected()
        if e is None:
            return
        cur_deg = math.degrees(rotation_of(e.transform))
        delta_deg = self._r.value() - cur_deg
        if abs(delta_deg) < 1e-6:
            return
        x0, y0, x1, y1 = e.world_bounding_box()
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rot = Matrix2D.rotation_deg(delta_deg)
        new_t = (
            Matrix2D.translation(cx, cy)
            @ rot
            @ Matrix2D.translation(-cx, -cy)
            @ e.transform
        )
        self._push_transform(e, new_t, "Rotazione")

    def _on_apply_layer(self) -> None:
        if self._updating:
            return
        e = self._single_selected()
        if e is None:
            return
        new_layer_id = self._layer.currentData()
        if not isinstance(new_layer_id, str) or new_layer_id == e.layer_id:
            return
        self._scene.undo_stack.push(
            ChangeEntityLayerCommand(self._document, e.id, new_layer_id)
        )