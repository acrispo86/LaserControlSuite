"""Console GRBL avanzata (dock destro, tabificato con CAM).

Funzionalità principali (Step 9b):

1.  Filtri di categoria indipendenti (ok / error / alarm / status / msg / tx)
2.  Colorazione sintattica delle righe (stile LightBurn)
3.  Timestamp opzionale
4.  Auto-scroll on/off con pausa automatica se l'utente scorre su
5.  Cronologia comandi (↑/↓ nel campo input)
6.  Contatore buffer ``Bf`` live dal controller (``bufferStateChanged``)
7.  Salva log su file
8.  Contatori di riga per categoria (status bar del pannello)
9.  Macro personalizzate persistenti (``ConsoleSettings``)
10. Ricerca nel log con evidenziazione

Step 9d: la console ascolta ``ThemeManager.themeChanged``, riapplica lo
stylesheet del widget log e ricostruisce il contenuto (i colori delle
righe sono già letti al volo dal proxy ``THEME``).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Slot
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lasercontrolsuite.comm import protocol as grbl
from lasercontrolsuite.comm.controller import GrblController
from lasercontrolsuite.comm.port_scanner import list_serial_ports
from lasercontrolsuite.config.console_settings import CATEGORIES, ConsoleSettings
from lasercontrolsuite.resources.theme import THEME
from lasercontrolsuite.resources.theme_manager import ThemeManager


BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 250000]

FILTER_CATEGORIES: tuple[str, ...] = ("ok", "error", "alarm", "status", "msg", "tx")

CATEGORY_LABELS = {
    "ok": "ok",
    "error": "err",
    "alarm": "alarm",
    "status": "status",
    "msg": "msg",
    "tx": "tx",
}


@dataclass
class LogLine:
    """Una riga del log della console."""

    category: str
    text: str
    timestamp: str = ""


class ConsolePanel(QWidget):
    """Dock widget per il controllo manuale GRBL e il monitoraggio streaming."""

    MAX_LINES = 4000

    def __init__(
        self,
        controller: GrblController,
        parent: QWidget | None = None,
        *,
        settings: ConsoleSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._settings = settings if settings is not None else ConsoleSettings()

        self._lines: list[LogLine] = []
        self._counts: dict[str, int] = {c: 0 for c in CATEGORIES}
        self._history: list[str] = []
        self._history_index = 0
        self._inflight: int = 0
        self._buffer_size: int = GrblController.RX_BUFFER_SIZE
        self._autoscroll_paused: bool = False
        self._suppress_scroll_check: bool = False
        self._search_text: str = ""

        self._show: dict[str, bool] = self._settings.get_all_show()

        self._build_ui()
        self._restore_settings()
        self._connect_signals()
        self.refresh_ports()
        self._rebuild_log()
        self._update_counts_label()

        ThemeManager.instance().themeChanged.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        conn_box = QGroupBox("Connection")
        conn = QGridLayout(conn_box)
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._baud_combo = QComboBox()
        for b in BAUD_RATES:
            self._baud_combo.addItem(str(b), b)
        self._baud_combo.setCurrentText("115200")
        self._refresh_btn = QPushButton("Refresh")
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setCheckable(True)
        conn.addWidget(QLabel("Port:"), 0, 0)
        conn.addWidget(self._port_combo, 0, 1)
        conn.addWidget(self._refresh_btn, 0, 2)
        conn.addWidget(QLabel("Baud:"), 1, 0)
        conn.addWidget(self._baud_combo, 1, 1)
        conn.addWidget(self._connect_btn, 1, 2)
        layout.addWidget(conn_box)

        ctrl_box = QGroupBox("Control")
        ctrl = QGridLayout(ctrl_box)
        self._home_btn = QPushButton("Home ($H)")
        self._unlock_btn = QPushButton("Unlock ($X)")
        self._reset_btn = QPushButton("Reset")
        self._pause_btn = QPushButton("Pause")
        self._resume_btn = QPushButton("Resume")
        self._status_btn = QPushButton("Status")
        ctrl.addWidget(self._home_btn, 0, 0)
        ctrl.addWidget(self._unlock_btn, 0, 1)
        ctrl.addWidget(self._reset_btn, 0, 2)
        ctrl.addWidget(self._pause_btn, 1, 0)
        ctrl.addWidget(self._resume_btn, 1, 1)
        ctrl.addWidget(self._status_btn, 1, 2)
        layout.addWidget(ctrl_box)

        jog_box = QGroupBox("Jog")
        jog = QGridLayout(jog_box)
        self._jog_step_combo = QComboBox()
        for s in (0.1, 1.0, 5.0, 10.0, 50.0):
            self._jog_step_combo.addItem(f"{s} mm", s)
        self._jog_step_combo.setCurrentIndex(1)
        self._jog_feed_edit = QLineEdit("1000")
        self._jog_x_neg = QPushButton("X-")
        self._jog_x_pos = QPushButton("X+")
        self._jog_y_neg = QPushButton("Y-")
        self._jog_y_pos = QPushButton("Y+")
        jog.addWidget(QLabel("Step:"), 0, 0)
        jog.addWidget(self._jog_step_combo, 0, 1)
        jog.addWidget(QLabel("Feed:"), 0, 2)
        jog.addWidget(self._jog_feed_edit, 0, 3)
        jog.addWidget(self._jog_x_neg, 1, 0)
        jog.addWidget(self._jog_x_pos, 1, 1)
        jog.addWidget(self._jog_y_neg, 1, 2)
        jog.addWidget(self._jog_y_pos, 1, 3)
        layout.addWidget(jog_box)

        layout.addLayout(self._build_log_toolbar())

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setUndoRedoEnabled(False)
        self._log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mono = QFont(THEME.font_mono)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(THEME.font_size)
        self._log.setFont(mono)
        self._apply_log_style()
        layout.addWidget(self._log, stretch=1)

        inp = QHBoxLayout()
        self._macro_combo = QComboBox()
        self._macro_combo.setEditable(False)
        self._macro_combo.setMinimumWidth(90)
        self._macro_combo.setToolTip("Macro personalizzate (salva/elimina)")
        self._macro_add_btn = QToolButton()
        self._macro_add_btn.setText("+")
        self._macro_add_btn.setToolTip("Salva il contenuto dell'input come macro")
        self._macro_del_btn = QToolButton()
        self._macro_del_btn.setText("−")
        self._macro_del_btn.setToolTip("Elimina la macro selezionata")

        self._input = QLineEdit()
        self._input.setPlaceholderText("Command… (e.g. $$, ?) — ↑/↓ per la cronologia")
        self._input.installEventFilter(self)
        self._send_btn = QPushButton("Send")

        inp.addWidget(self._macro_combo)
        inp.addWidget(self._macro_add_btn)
        inp.addWidget(self._macro_del_btn)
        inp.addWidget(self._input, stretch=1)
        inp.addWidget(self._send_btn)
        layout.addLayout(inp)

        self._status_label = QLabel("Disconnected")
        self._status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self._status_label)

    def _apply_log_style(self) -> None:
        self._log.setStyleSheet(
            f"QPlainTextEdit {{"
            f"  background-color: {THEME.console_bg};"
            f"  color: {THEME.fg_primary};"
            f"  border: 1px solid {THEME.border};"
            f"}}"
        )

    def _on_theme_changed(self, _name: str) -> None:
        self._apply_log_style()
        self._rebuild_log()

    def _build_log_toolbar(self) -> QVBoxLayout:
        root = QVBoxLayout()
        root.setSpacing(4)

        row1 = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("🔍 Cerca nel log…")
        self._search_edit.setClearButtonEnabled(True)
        row1.addWidget(self._search_edit, stretch=1)

        self._timestamp_btn = QToolButton()
        self._timestamp_btn.setText("⏱")
        self._timestamp_btn.setCheckable(True)
        self._timestamp_btn.setToolTip("Mostra timestamp HH:MM:SS su ogni riga")

        self._autoscroll_btn = QToolButton()
        self._autoscroll_btn.setText("⬇")
        self._autoscroll_btn.setCheckable(True)
        self._autoscroll_btn.setToolTip("Auto-scroll attivo (pausa automatica se scorri su)")

        self._save_btn = QToolButton()
        self._save_btn.setText("💾")
        self._save_btn.setToolTip("Salva log su file…")

        self._clear_btn = QToolButton()
        self._clear_btn.setText("🧹")
        self._clear_btn.setToolTip("Svuota il log")

        row1.addWidget(self._timestamp_btn)
        row1.addWidget(self._autoscroll_btn)
        row1.addWidget(self._save_btn)
        row1.addWidget(self._clear_btn)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Filtri:"))
        self._filter_checks: dict[str, QCheckBox] = {}
        for cat in FILTER_CATEGORIES:
            cb = QCheckBox(CATEGORY_LABELS.get(cat, cat))
            cb.setToolTip(f"Mostra righe di categoria '{cat}'")
            cb.setProperty("category", cat)
            self._filter_checks[cat] = cb
            row2.addWidget(cb)
        row2.addStretch(1)
        root.addLayout(row2)

        return root

    def _restore_settings(self) -> None:
        for cat, cb in self._filter_checks.items():
            cb.setChecked(self._show.get(cat, True))
        self._timestamp_btn.setChecked(self._settings.get_timestamp())
        self._autoscroll_btn.setChecked(self._settings.get_autoscroll())
        self._reload_macros()

    def _reload_macros(self) -> None:
        self._macro_combo.blockSignals(True)
        self._macro_combo.clear()
        self._macro_combo.addItem("Macro…", "")
        for cmd in self._settings.get_macros():
            self._macro_combo.addItem(cmd, cmd)
        self._macro_combo.setCurrentIndex(0)
        self._macro_combo.blockSignals(False)

    def _connect_signals(self) -> None:
        self._refresh_btn.clicked.connect(self.refresh_ports)
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        self._send_btn.clicked.connect(self._on_send)
        self._input.returnPressed.connect(self._on_send)
        self._clear_btn.clicked.connect(self._on_clear_log)
        self._save_btn.clicked.connect(self._on_save_log)

        self._home_btn.clicked.connect(self._controller.home)
        self._unlock_btn.clicked.connect(self._controller.unlock)
        self._reset_btn.clicked.connect(self._controller.soft_reset)
        self._pause_btn.clicked.connect(self._controller.feed_hold)
        self._resume_btn.clicked.connect(self._controller.resume)
        self._status_btn.clicked.connect(self._controller.status_query)

        self._jog_x_neg.clicked.connect(lambda: self._jog(-self._jog_step(), 0.0))
        self._jog_x_pos.clicked.connect(lambda: self._jog(+self._jog_step(), 0.0))
        self._jog_y_neg.clicked.connect(lambda: self._jog(0.0, -self._jog_step()))
        self._jog_y_pos.clicked.connect(lambda: self._jog(0.0, +self._jog_step()))

        for cat, cb in self._filter_checks.items():
            cb.toggled.connect(lambda checked, c=cat: self._on_filter_toggled(c, checked))

        self._timestamp_btn.toggled.connect(self._on_timestamp_toggled)
        self._autoscroll_btn.toggled.connect(self._on_autoscroll_toggled)
        self._search_edit.textChanged.connect(self._on_search_changed)

        self._macro_combo.activated.connect(self._on_macro_activated)
        self._macro_add_btn.clicked.connect(self._on_macro_add)
        self._macro_del_btn.clicked.connect(self._on_macro_del)

        self._log.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

        self._controller.connected.connect(self._on_connected)
        self._controller.disconnected.connect(self._on_disconnected)
        self._controller.lineReceived.connect(self._on_line)
        self._controller.errorOccurred.connect(self._on_transport_error)
        self._controller.bufferStateChanged.connect(self._on_buffer_state)
        self._controller.progressChanged.connect(self._on_progress)

    # ------------------------------------------------------------------
    # Helpers (invariati dal 9b)
    # ------------------------------------------------------------------

    def _jog_step(self) -> float:
        data = self._jog_step_combo.currentData()
        return float(data) if data is not None else 1.0

    def _jog(self, dx: float, dy: float) -> None:
        try:
            feed = float(self._jog_feed_edit.text())
        except ValueError:
            feed = 1000.0
        self._controller.jog(dx, dy, feed)

    def _selected_port(self) -> str:
        data = self._port_combo.currentData()
        if data:
            return str(data)
        return self._port_combo.currentText().strip()

    def _append_line(self, category: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S") if self._timestamp_btn.isChecked() else ""
        self._lines.append(LogLine(category=category, text=text, timestamp=ts))
        if len(self._lines) > self.MAX_LINES:
            removed = self._lines[: len(self._lines) - self.MAX_LINES]
            self._lines = self._lines[-self.MAX_LINES :]
            for r in removed:
                if r.category in self._counts and self._counts[r.category] > 0:
                    self._counts[r.category] -= 1

        if category in self._counts:
            self._counts[category] += 1

        if not self._show.get(category, True):
            self._update_counts_label()
            return

        html_line = self._render_line_html(self._lines[-1])
        self._log.appendHtml(html_line)
        self._update_counts_label()
        self._maybe_scroll_to_bottom()

    def _render_line_html(self, line: LogLine) -> str:
        color = THEME.console_color_for(line.category)
        ts = ""
        if line.timestamp:
            ts = f'<span style="color:{THEME.console_timestamp};">[{line.timestamp}] </span>'

        prefix = self._category_prefix(line.category)
        safe = html.escape(line.text)
        safe = self._apply_search_highlight(safe)

        return (
            f'<div style="white-space: pre-wrap; margin: 0;">'
            f'{ts}'
            f'<span style="color:{color};">{prefix}{safe}</span>'
            f'</div>'
        )

    @staticmethod
    def _category_prefix(category: str) -> str:
        return {
            "tx": "&gt; ",
            "ok": "&lt; ",
            "error": "!! ",
            "alarm": "!! ",
            "status": "&lt; ",
            "msg": "&lt; ",
            "welcome": "",
            "info": "",
        }.get(category, "")

    def _apply_search_highlight(self, safe_text: str) -> str:
        if not self._search_text:
            return safe_text
        needle = html.escape(self._search_text)
        if not needle:
            return safe_text
        lowered = safe_text.lower()
        needle_lower = needle.lower()
        out: list[str] = []
        i = 0
        while True:
            j = lowered.find(needle_lower, i)
            if j == -1:
                out.append(safe_text[i:])
                break
            out.append(safe_text[i:j])
            out.append(
                f'<span style="background-color:{THEME.console_search_hl_bg};'
                f' color:{THEME.console_search_hl_fg};">'
                f'{safe_text[j:j + len(needle)]}</span>'
            )
            i = j + len(needle)
        return "".join(out)

    def _rebuild_log(self) -> None:
        self._suppress_scroll_check = True
        self._log.clear()
        visible = [ln for ln in self._lines if self._show.get(ln.category, True)]
        chunks = [self._render_line_html(ln) for ln in visible]
        if chunks:
            self._log.appendHtml("".join(chunks))
        self._suppress_scroll_check = False
        self._maybe_scroll_to_bottom()

    def _maybe_scroll_to_bottom(self) -> None:
        if not self._autoscroll_btn.isChecked():
            return
        if self._autoscroll_paused:
            return
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_counts_label(self) -> None:
        parts = []
        for cat in FILTER_CATEGORIES:
            label = CATEGORY_LABELS.get(cat, cat)
            parts.append(f"{label}: {self._counts.get(cat, 0)}")
        parts.append(f"Bf: {self._inflight}/{self._buffer_size}")
        self._status_label.setText(" | ".join(parts))

    # ------------------------------------------------------------------
    # Slots (invariati dal 9b)
    # ------------------------------------------------------------------

    @Slot()
    def refresh_ports(self) -> None:
        previous = self._selected_port()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        for p in list_serial_ports():
            label = p["device"]
            if p.get("description"):
                label = f"{p['device']} — {p['description']}"
            self._port_combo.addItem(label, p["device"])
        self._port_combo.blockSignals(False)
        if previous:
            for i in range(self._port_combo.count()):
                if (self._port_combo.itemData(i) == previous
                        or self._port_combo.itemText(i) == previous):
                    self._port_combo.setCurrentIndex(i)
                    break

    @Slot()
    def _on_connect_clicked(self) -> None:
        if self._connect_btn.isChecked():
            port = self._selected_port()
            if not port:
                self._append_line("info", "[no port selected]")
                self._connect_btn.setChecked(False)
                return
            try:
                baud = int(self._baud_combo.currentText())
            except ValueError:
                baud = 115200
            self._controller.connect_port(port, baud)
        else:
            self._controller.disconnect_port()

    @Slot(str, int)
    def _on_connected(self, port: str, baud: int) -> None:
        self._connect_btn.setChecked(True)
        self._connect_btn.setText("Disconnect")
        self._append_line("info", f"--- Connected to {port} @ {baud} ---")

    @Slot()
    def _on_disconnected(self) -> None:
        self._connect_btn.setChecked(False)
        self._connect_btn.setText("Connect")
        self._append_line("info", "--- Disconnected ---")

    @Slot(str)
    def _on_line(self, line: str) -> None:
        if line == "ok":
            self._append_line("ok", "ok")
            return
        err = grbl.parse_error(line)
        if err is not None:
            self._append_line("error", f"error:{err} — {grbl.describe_error(err)}")
            return
        alarm = grbl.parse_alarm(line)
        if alarm is not None:
            self._append_line("alarm", f"ALARM:{alarm} — {grbl.describe_alarm(alarm)}")
            return
        status = grbl.parse_status(line)
        if status is not None:
            st = status.get("state", "?")
            pos = status.get("wpos") or status.get("mpos")
            if pos:
                self._append_line(
                    "status",
                    f"{st}  X={pos[0]:.2f}  Y={pos[1]:.2f}  Z={pos[2]:.2f}",
                )
            else:
                self._append_line("status", st)
            return
        fb = grbl.parse_feedback(line)
        if fb is not None:
            self._append_line("msg", fb)
            return
        welcome = grbl.parse_welcome(line)
        if welcome is not None:
            self._append_line("welcome", welcome)
            return
        self._append_line("msg", line)

    @Slot(str)
    def _on_transport_error(self, err: str) -> None:
        self._append_line("error", err)

    @Slot(int, int)
    def _on_buffer_state(self, inflight: int, size: int) -> None:
        self._inflight = int(inflight)
        self._buffer_size = int(size) or GrblController.RX_BUFFER_SIZE
        self._update_counts_label()

    @Slot(int, int)
    def _on_progress(self, sent: int, total: int) -> None:
        if total > 0:
            self._append_line("info", f"--- Streaming {sent}/{total} ---")

    @Slot()
    def _on_clear_log(self) -> None:
        self._lines.clear()
        for c in self._counts:
            self._counts[c] = 0
        self._log.clear()
        self._update_counts_label()

    @Slot()
    def _on_save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva log console", "console.log",
            "Log (*.log *.txt);;Tutti i file (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for ln in self._lines:
                    ts = f"[{ln.timestamp}] " if ln.timestamp else ""
                    f.write(f"{ts}{ln.category.upper():7s} {ln.text}\n")
        except OSError as exc:
            QMessageBox.critical(self, "Errore salvataggio", str(exc))
            return
        self._append_line("info", f"--- Log salvato in {Path(path).name} ---")

    @Slot(str, bool)
    def _on_filter_toggled(self, category: str, checked: bool) -> None:
        self._show[category] = bool(checked)
        self._settings.set_show_category(category, bool(checked))
        self._rebuild_log()

    @Slot(bool)
    def _on_timestamp_toggled(self, checked: bool) -> None:
        self._settings.set_timestamp(bool(checked))
        self._append_line("info", "--- Timestamp " + ("ON" if checked else "OFF") + " ---")

    @Slot(bool)
    def _on_autoscroll_toggled(self, checked: bool) -> None:
        self._settings.set_autoscroll(bool(checked))
        if checked:
            self._autoscroll_paused = False
            self._maybe_scroll_to_bottom()

    @Slot(str)
    def _on_search_changed(self, text: str) -> None:
        self._search_text = text or ""
        self._rebuild_log()

    @Slot(int)
    def _on_scroll_changed(self, value: int) -> None:
        if self._suppress_scroll_check:
            return
        sb = self._log.verticalScrollBar()
        at_bottom = value >= sb.maximum()
        if self._autoscroll_btn.isChecked():
            self._autoscroll_paused = not at_bottom

    @Slot(int)
    def _on_macro_activated(self, index: int) -> None:
        if index <= 0:
            return
        cmd = self._macro_combo.itemData(index) or ""
        if cmd:
            self._input.setText(cmd)
            self._input.setFocus()
        self._macro_combo.setCurrentIndex(0)

    @Slot()
    def _on_macro_add(self) -> None:
        cmd = self._input.text().strip()
        if not cmd:
            QMessageBox.information(self, "Macro", "Digita un comando nell'input prima di salvarlo.")
            return
        self._settings.add_macro(cmd)
        self._reload_macros()
        self._append_line("info", f"--- Macro salvata: {cmd} ---")

    @Slot()
    def _on_macro_del(self) -> None:
        idx = self._macro_combo.currentIndex()
        if idx <= 0:
            QMessageBox.information(self, "Macro", "Seleziona una macro da eliminare.")
            return
        cmd = self._macro_combo.itemData(idx) or ""
        if not cmd:
            return
        self._settings.remove_macro(cmd)
        self._reload_macros()
        self._append_line("info", f"--- Macro rimossa: {cmd} ---")

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            key = event.key()
            if key == Qt.Key.Key_Up:
                self._history_prev()
                return True
            if key == Qt.Key.Key_Down:
                self._history_next()
                return True
        return super().eventFilter(obj, event)

    def _history_prev(self) -> None:
        if not self._history:
            return
        if self._history_index > 0:
            self._history_index -= 1
        self._input.setText(self._history[self._history_index])
        self._input.setCursorPosition(len(self._input.text()))

    def _history_next(self) -> None:
        if not self._history:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._input.setText(self._history[self._history_index])
        else:
            self._history_index = len(self._history)
            self._input.clear()
        self._input.setCursorPosition(len(self._input.text()))

    @Slot()
    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._append_line("tx", text)
        self._history.append(text)
        self._history_index = len(self._history)
        self._controller.send_line(text)
        self._input.clear()

    # ------------------------------------------------------------------
    # Introspection (for tests)
    # ------------------------------------------------------------------

    @property
    def log_widget(self) -> QPlainTextEdit:
        return self._log

    @property
    def controller(self) -> GrblController:
        return self._controller

    @property
    def settings(self) -> ConsoleSettings:
        return self._settings

    @property
    def lines(self) -> list[LogLine]:
        return list(self._lines)

    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def history(self) -> list[str]:
        return list(self._history)