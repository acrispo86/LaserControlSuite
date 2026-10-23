"""Dialog per l'anteprima grafica e testuale del G-code.

Layout: splitter verticale.
  * sopra: ``CamPreviewView``
  * sotto: testo del G-code (con pulsante Salva)

Esc: se la preview ha una selezione, la deseleziona; altrimenti chiude.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)

from lasercontrolsuite.cam.preview import PreviewScene
from lasercontrolsuite.config import Machine
from lasercontrolsuite.resources.theme import THEME
from lasercontrolsuite.ui.widgets.cam_preview import CamPreviewView


class GCodeViewerDialog(QDialog):
    """Anteprima grafica + testuale del G-code generato."""

    def __init__(
        self,
        gcode: str,
        stats_text: str = "",
        *,
        preview_scene: PreviewScene | None = None,
        machine: Machine | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Anteprima G-code")
        self.resize(1100, 800)

        layout = QVBoxLayout(self)

        header = QLabel(stats_text or "G-code generato", self)
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Vertical, self)

        self._preview_view: CamPreviewView | None = None
        if preview_scene is not None and machine is not None:
            self._preview_view = CamPreviewView(preview_scene, machine, self)
            splitter.addWidget(self._preview_view)

        self._text = QPlainTextEdit(self)
        self._text.setPlainText(gcode)
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont(THEME.font_mono)
        font.setPointSize(9)
        self._text.setFont(font)
        splitter.addWidget(self._text)

        if self._preview_view is not None:
            splitter.setSizes([int(self.height() * 0.6), int(self.height() * 0.4)])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(self)
        save = QPushButton("Salva come…", self)
        close = QPushButton("Chiudi", self)
        buttons.addButton(save, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(close, QDialogButtonBox.ButtonRole.RejectRole)
        save.clicked.connect(self._on_save)
        close.clicked.connect(self.reject)
        layout.addWidget(buttons)

        if self._preview_view is not None:
            self._preview_view.setFocus()

    # ------------------------------------------------------------------ API
    @property
    def gcode_text(self) -> str:
        return self._text.toPlainText()

    @property
    def preview_view(self) -> CamPreviewView | None:
        return self._preview_view

    # ---------------------------------------------------------------- events
    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Esc: prima deseleziona, poi chiude."""
        if event.key() == Qt.Key.Key_Escape and self._preview_view is not None:
            if self._preview_view.has_selection():
                self._preview_view.clear_selection()
                event.accept()
                return
        super().keyPressEvent(event)

    # ---------------------------------------------------------------- actions
    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva G-code",
            "job.nc",
            "G-code (*.nc *.gcode *.tap);;Tutti i file (*)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._text.toPlainText())
        except OSError as exc:
            QMessageBox.critical(self, "Errore salvataggio", str(exc))