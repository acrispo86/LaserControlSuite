"""Test del pannello Console GRBL avanzato (Step 9b).

Nota su pytest-qt e segnali cross-thread
----------------------------------------
I segnali `GrblController.connected` e `GrblController.lineReceived` sono
emessi dal thread di lavoro e consegnati alla main thread via
`QueuedConnection`. In pytest-qt 4.5 + Qt 6.12 + Windows:

- `qtbot.waitSignal` e `qtbot.waitUntil` non consegnano in modo affidabile
  questi segnali quando c'è una UI agganciata.
- `qtbot.wait(ms)` **singolo** non dà il tempo al worker di processare la
  seriale e di emettere il segnale: durante i 300 ms la main thread è in un
  loop C++ che non cede il GIL al worker, che quindi non riesce a leggere
  dalla seriale (fake) né a emettere `lineReceived`.
- Il pattern robusto è un **loop esplicito** che alterna
  `QCoreApplication.processEvents(AllEvents)` e `qtbot.wait(POLL_MS)`.

Per questo usiamo gli helper `_connect_and_wait` e `_wait_until` per
**tutte** le attese sui segnali del controller, e **mai** un
`qtbot.wait(N)` singolo dopo `fake.push_response(...)`.
"""
from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QSettings

from lasercontrolsuite.comm.controller import GrblController
from lasercontrolsuite.comm.fake_serial import FakeSerialPort
from lasercontrolsuite.config.console_settings import ConsoleSettings
from lasercontrolsuite.ui.panels.console_panel import ConsolePanel


CONNECT_TIMEOUT_MS = 8000
WAIT_TIMEOUT_MS = 3000
POLL_MS = 20


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _pump(qtbot, ms: int = POLL_MS) -> None:
    """Processa eventi Qt + cede il GIL al worker thread."""
    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    qtbot.wait(ms)


def _connect_and_wait(
    ctrl: GrblController,
    qtbot,
    port: str = "FAKE",
    baud: int = 115200,
    timeout_ms: int = CONNECT_TIMEOUT_MS,
) -> tuple[str, int]:
    """Connetti e attendi `connected` (loop esplicito, non `waitSignal`)."""
    received: list[tuple[str, int]] = []
    ctrl.connected.connect(lambda p, b: received.append((p, b)))
    ctrl.connect_port(port, baud)

    deadline = time.time() + timeout_ms / 1000.0
    while not received and time.time() < deadline:
        _pump(qtbot)

    assert received, (
        f"connected non ricevuto entro {timeout_ms} ms "
        f"(port={port!r}, baud={baud}). isRunning={ctrl.isRunning()}"
    )
    return received[-1]


def _wait_until(qtbot, predicate, timeout_ms: int = WAIT_TIMEOUT_MS) -> bool:
    """Attende `predicate()` con loop esplicito.

    Alterna `processEvents` e `qtbot.wait(POLL_MS)` per dare al worker
    thread la possibilità di avanzare (leggere la seriale, emettere segnali)
    mentre la main thread processa eventi Qt.
    """
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        if predicate():
            return True
        _pump(qtbot)
    return predicate()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_settings(tmp_path):
    """QSettings isolato su file INI in tmp_path."""
    ini = tmp_path / "console.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    yield ConsoleSettings(qs)
    qs.clear()
    qs.sync()


@pytest.fixture
def wired(qapp, isolated_settings):
    """Controller + FakeSerialPort + ConsolePanel, con teardown pulito."""
    fake = FakeSerialPort()
    ctrl = GrblController(serial_factory=lambda port, baud: fake)
    ctrl.start()
    panel = ConsolePanel(ctrl, settings=isolated_settings)
    yield ctrl, fake, panel, isolated_settings
    ctrl.shutdown()
    ctrl.wait(2000)
    panel.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# Smoke + diagnostic
# ---------------------------------------------------------------------------

def test_panel_builds(wired):
    _ctrl, _fake, panel, _s = wired
    assert panel.log_widget is not None
    assert panel.controller is not None
    assert panel.settings is not None


def test_diagnostic_connected_signal_is_emitted(wired, qtbot):
    """Guardia: il segnale `connected` DEVE essere emesso dal controller."""
    ctrl, fake, panel, _s = wired
    assert ctrl.isRunning(), "thread worker non è partito"
    assert not fake.is_open, "fake serial non dovrebbe essere aperto prima di connect"

    port, baud = _connect_and_wait(ctrl, qtbot)

    assert port == "FAKE"
    assert baud == 115200
    assert fake.is_open, "il fake serial dovrebbe essere aperto dopo connect"


def test_diagnostic_line_received_from_controller(wired, qtbot):
    """Guardia: `lineReceived` DEVE arrivare dal controller dopo push_response.

    Bypassa il pannello: connette uno spy diretto al segnale.
    Se questo test fallisce, il bug è nel controller (o nel worker),
    non nel pannello o nell'interazione con pytest-qt.
    """
    ctrl, fake, panel, _s = wired
    received: list[str] = []
    ctrl.lineReceived.connect(lambda line: received.append(line))

    _connect_and_wait(ctrl, qtbot)

    assert ctrl.isRunning()
    assert fake.is_open

    fake.push_response("ok")
    got = _wait_until(qtbot, lambda: bool(received), timeout_ms=2000)

    assert got, (
        f"lineReceived non emesso entro 2s. "
        f"isRunning={ctrl.isRunning()}, "
        f"fake.is_open={fake.is_open}, "
        f"rx={bytes(fake._rx)!r}"
    )
    assert received[-1] == "ok"


# ---------------------------------------------------------------------------
# Invio manuale
# ---------------------------------------------------------------------------

def test_manual_send_reaches_serial(wired, qtbot):
    ctrl, fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)

    panel._input.setText("$$")
    panel._on_send()

    got = _wait_until(qtbot, lambda: "$$" in fake.sent_lines(), timeout_ms=2000)
    assert got, "$$ non arrivato al fake serial"
    assert panel.counts()["tx"] == 1


# ---------------------------------------------------------------------------
# Classificazione delle righe
# ---------------------------------------------------------------------------

def test_line_ok_classified(wired, qtbot):
    ctrl, fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)
    fake.push_response("ok")
    got = _wait_until(qtbot, lambda: panel.counts()["ok"] >= 1, timeout_ms=2000)
    assert got, (
        f"ok non classificato. "
        f"counts={panel.counts()}, lines={[l.text for l in panel.lines]}"
    )


def test_line_error_classified(wired, qtbot):
    ctrl, fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)
    fake.push_response("error:9")
    got = _wait_until(qtbot, lambda: panel.counts()["error"] >= 1, timeout_ms=2000)
    assert got, f"error non classificato. lines={[l.text for l in panel.lines]}"


def test_line_alarm_classified(wired, qtbot):
    ctrl, fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)
    fake.push_response("ALARM:1")
    got = _wait_until(qtbot, lambda: panel.counts()["alarm"] >= 1, timeout_ms=2000)
    assert got, f"alarm non classificato. lines={[l.text for l in panel.lines]}"


def test_line_status_classified(wired, qtbot):
    ctrl, fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)
    fake.push_response("<Idle|MPos:1.00,2.00,0.00>")
    got = _wait_until(qtbot, lambda: panel.counts()["status"] >= 1, timeout_ms=2000)
    assert got, f"status non classificato. lines={[l.text for l in panel.lines]}"


def test_line_feedback_is_msg(wired, qtbot):
    ctrl, fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)
    fake.push_response("[MSG:hello]")
    got = _wait_until(qtbot, lambda: panel.counts()["msg"] >= 1, timeout_ms=2000)
    assert got, f"msg non classificato. lines={[l.text for l in panel.lines]}"


# ---------------------------------------------------------------------------
# Filtri
# ---------------------------------------------------------------------------

def test_ok_hidden_when_filter_off(wired, qtbot):
    ctrl, fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)

    panel._filter_checks["ok"].setChecked(False)
    fake.push_response("ok")

    # PRIMA attende che il messaggio sia arrivato in memoria (lo spy è il
    # contatore, indipendente dal filtro di visibilità).
    got = _wait_until(qtbot, lambda: panel.counts()["ok"] >= 1, timeout_ms=2000)
    assert got, "il messaggio non è arrivato (impossibile testare il filtro)"

    visible_cats = {
        ln.category for ln in panel.lines if panel._show.get(ln.category, True)
    }
    assert "ok" not in visible_cats


# ---------------------------------------------------------------------------
# Timestamp / Autoscroll
# ---------------------------------------------------------------------------

def test_timestamp_toggle_persists(wired, qtbot):
    _ctrl, _fake, panel, settings = wired
    panel._timestamp_btn.setChecked(True)
    assert settings.get_timestamp() is True
    panel._timestamp_btn.setChecked(False)
    assert settings.get_timestamp() is False


def test_autoscroll_toggle_persists(wired):
    _ctrl, _fake, panel, settings = wired
    panel._autoscroll_btn.setChecked(False)
    assert settings.get_autoscroll() is False
    panel._autoscroll_btn.setChecked(True)
    assert settings.get_autoscroll() is True


# ---------------------------------------------------------------------------
# Cronologia comandi
# ---------------------------------------------------------------------------

def test_command_history_up_down(wired, qtbot):
    ctrl, _fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)

    panel._input.setText("$$")
    panel._on_send()
    panel._input.setText("?")
    panel._on_send()

    panel._history_prev()
    assert panel._input.text() == "?"
    panel._history_prev()
    assert panel._input.text() == "$$"
    panel._history_next()
    assert panel._input.text() == "?"
    panel._history_next()
    assert panel._input.text() == ""


# ---------------------------------------------------------------------------
# Buffer
# ---------------------------------------------------------------------------

def test_buffer_state_label_updates(wired, qtbot):
    ctrl, _fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)
    panel._on_buffer_state(17, 128)
    assert "Bf: 17/128" in panel._status_label.text()


# ---------------------------------------------------------------------------
# Macro
# ---------------------------------------------------------------------------

def test_macro_add_and_remove(wired, isolated_settings):
    _ctrl, _fake, panel, settings = wired
    panel._input.setText("G28")
    panel._on_macro_add()
    assert "G28" in settings.get_macros()

    idx = next(
        i for i in range(panel._macro_combo.count())
        if panel._macro_combo.itemData(i) == "G28"
    )
    panel._macro_combo.setCurrentIndex(idx)
    panel._on_macro_del()
    assert "G28" not in settings.get_macros()


# ---------------------------------------------------------------------------
# Ricerca
# ---------------------------------------------------------------------------

def test_search_highlights_visible_text(wired, qtbot):
    ctrl, fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)
    fake.push_response("[MSG:unique_marker_xyz]")

    got = _wait_until(qtbot, lambda: panel.counts()["msg"] >= 1, timeout_ms=2000)
    assert got, "il messaggio univoco non è arrivato"

    panel._search_edit.setText("unique_marker_xyz")
    assert "unique_marker_xyz" in panel.log_widget.toPlainText()


# ---------------------------------------------------------------------------
# Clear log
# ---------------------------------------------------------------------------

def test_clear_log_resets_counts(wired, qtbot):
    ctrl, fake, panel, _s = wired
    _connect_and_wait(ctrl, qtbot)
    fake.push_response("ok")

    got = _wait_until(qtbot, lambda: panel.counts()["ok"] >= 1, timeout_ms=2000)
    assert got, "ok non arrivato"

    panel._on_clear_log()
    assert panel.counts()["ok"] == 0
    assert panel.log_widget.toPlainText() == ""