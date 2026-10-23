"""Dialog per i parametri del tracing immagine."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from lasercontrolsuite.cad.io.image_importer import ImageTraceOptions


class TraceDialog(QDialog):
    """Chiede i parametri del tracing immagine all'utente."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Traccia immagine")
        self.setModal(True)
        self.resize(420, 400)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Opzioni di tracciamento. Outline = contorni pieni, "
            "Centerline = linea centrale (scheletro)."
        ))

        form = QFormLayout()

        self._mode = QComboBox(self)
        self._mode.addItem("Contorni (outline)", "outline")
        self._mode.addItem("Linea centrale (centerline)", "centerline")
        self._mode.addItem("Entrambi", "both")
        form.addRow("Modalità:", self._mode)

        self._threshold = QSpinBox(self)
        self._threshold.setRange(-1, 255)
        self._threshold.setValue(-1)  # -1 = Otsu automatico
        self._threshold.setSpecialValueText("Otsu automatico")
        form.addRow("Soglia (0-255):", self._threshold)

        self._invert = QCheckBox("Primo piano = parte chiara", self)
        form.addRow("", self._invert)

        self._blur = QSpinBox(self)
        self._blur.setRange(0, 31)
        self._blur.setValue(0)
        form.addRow("Blur (px):", self._blur)

        self._epsilon = QDoubleSpinBox(self)
        self._epsilon.setRange(0.0, 20.0)
        self._epsilon.setSingleStep(0.5)
        self._epsilon.setValue(1.0)
        self._epsilon.setDecimals(2)
        form.addRow("Semplificazione (px):", self._epsilon)

        self._min_area = QDoubleSpinBox(self)
        self._min_area.setRange(0.0, 100000.0)
        self._min_area.setValue(4.0)
        self._min_area.setDecimals(2)
        form.addRow("Area minima (px²):", self._min_area)

        self._min_length = QSpinBox(self)
        self._min_length.setRange(1, 1000)
        self._min_length.setValue(3)
        form.addRow("Lunghezza minima (px):", self._min_length)

        self._prune = QSpinBox(self)
        self._prune.setRange(0, 200)
        self._prune.setValue(6)
        form.addRow("Prune rami corti (px):", self._prune)

        self._max_side = QSpinBox(self)
        self._max_side.setRange(0, 20000)
        self._max_side.setValue(0)
        self._max_side.setSpecialValueText("Nessun limite")
        form.addRow("Lato massimo (px):", self._max_side)

        self._dpi = QDoubleSpinBox(self)
        self._dpi.setRange(1.0, 2000.0)
        self._dpi.setValue(96.0)
        self._dpi.setDecimals(0)
        form.addRow("DPI immagine:", self._dpi)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def options(self) -> ImageTraceOptions:
        threshold = self._threshold.value()
        max_side = self._max_side.value()
        return ImageTraceOptions(
            mode=self._mode.currentData(),
            threshold=None if threshold < 0 else threshold,
            invert=self._invert.isChecked(),
            blur=self._blur.value(),
            max_side=None if max_side <= 0 else max_side,
            epsilon=self._epsilon.value(),
            min_area=self._min_area.value(),
            min_length=self._min_length.value(),
            prune=self._prune.value(),
            dpi=self._dpi.value(),
        )