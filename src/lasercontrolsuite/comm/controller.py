"""GRBL controller: a QThread wrapping serial I/O with Qt signals.

Design notes
------------
* All public methods (``connect_port``, ``send_line``, ``jog``, ...) are
  **thread-safe**: they enqueue an operation which is executed inside
  ``run()``.
* Flow control follows GRBL's character-counting protocol: we never let
  the in-flight byte count exceed ``RX_BUFFER_SIZE`` and we decrement it
  on every ``ok`` or ``error:``.
* ``bufferStateChanged(inflight, size)`` is emitted whenever the in-flight
  byte count changes, so the console can show a live ``Bf`` indicator.
  In ``_do_connect`` it is emitted **after** ``connected`` so that the
  first event the UI receives is always "you are connected".
* The ``serial_factory`` hook allows tests to inject a ``FakeSerialPort``.
"""
from __future__ import annotations

import queue
from collections import deque
from typing import Callable, Optional

from PySide6.QtCore import QThread, Signal

from . import protocol as grbl


def _default_serial_factory(port: str, baud: int):
    """Open a real pyserial port. Imported lazily to keep pyserial optional."""
    import serial  # type: ignore
    return serial.Serial(port=port, baudrate=baud, timeout=0.05, write_timeout=1.0)


class GrblController(QThread):
    """Background thread managing a single GRBL connection."""

    # ---- signals ----
    connected = Signal(str, int)        # port, baud
    disconnected = Signal()
    statusReceived = Signal(dict)
    lineReceived = Signal(str)          # every raw incoming line
    messageReceived = Signal(str)       # [MSG:...] / welcome banner text
    errorOccurred = Signal(str)         # transport or local errors
    errorResponse = Signal(int)         # "error:N" from GRBL
    alarmReceived = Signal(int)         # "ALARM:N" from GRBL
    progressChanged = Signal(int, int)  # sent_lines, total_lines
    jobFinished = Signal(bool)          # True if completed, False if aborted
    bufferStateChanged = Signal(int, int)  # inflight_bytes, RX_BUFFER_SIZE

    # GRBL 1.1 serial RX buffer is 128 bytes.
    RX_BUFFER_SIZE = 128

    def __init__(
        self,
        serial_factory: Optional[Callable[[str, int], object]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._serial_factory = serial_factory or _default_serial_factory
        self._serial = None

        self._stop_requested = False
        self._commands: "queue.Queue[tuple[str, object]]" = queue.Queue()

        # Flow control state
        self._pending_lengths: deque[int] = deque()
        self._inflight = 0

        # Job state
        self._job_lines: list[str] = []
        self._job_total = 0
        self._job_sent = 0
        self._job_active = False

    # ------------------------------------------------------------------
    # Public, thread-safe API
    # ------------------------------------------------------------------

    def connect_port(self, port: str, baud: int = 115200) -> None:
        self._commands.put(("connect", (port, int(baud))))

    def disconnect_port(self) -> None:
        self._commands.put(("disconnect", None))

    def send_line(self, line: str) -> None:
        self._commands.put(("send", line))

    def send_realtime(self, byte: bytes) -> None:
        self._commands.put(("rt", byte))

    # Convenience wrappers --------------------------------------------------

    def home(self) -> None:
        self.send_line("$H")

    def unlock(self) -> None:
        self.send_line("$X")

    def soft_reset(self) -> None:
        self.send_realtime(b"\x18")

    def feed_hold(self) -> None:
        self.send_realtime(b"!")

    def resume(self) -> None:
        self.send_realtime(b"~")

    def status_query(self) -> None:
        self.send_realtime(b"?")

    def jog(self, dx: float = 0.0, dy: float = 0.0, feed: float = 1000.0) -> None:
        """Issue a jog move relative to the current position (mm)."""
        cmd = f"$J=G91G21X{dx:.3f}Y{dy:.3f}F{feed:.0f}"
        self.send_line(cmd)

    def stream_gcode(self, lines: list[str]) -> None:
        """Stream a list of G-code lines with GRBL flow control."""
        self._commands.put(("stream", list(lines)))

    def stop_job(self) -> None:
        """Abort the current job (soft reset)."""
        self._commands.put(("stop_job", None))

    def shutdown(self) -> None:
        """Request thread termination and wait for the loop to exit."""
        self._stop_requested = True
        self._commands.put(("quit", None))

    # ------------------------------------------------------------------
    # QThread main loop
    # ------------------------------------------------------------------

    def run(self) -> None:  # noqa: D401
        while not self._stop_requested:
            self._drain_commands()
            if self._serial is not None and getattr(self._serial, "is_open", False):
                self._poll_serial()
                self._try_send_job_lines()
                self.msleep(1)
            else:
                self.msleep(10)

        # Cleanup
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    # ------------------------------------------------------------------
    # Internals: command dispatch
    # ------------------------------------------------------------------

    def _drain_commands(self) -> None:
        while True:
            try:
                cmd, arg = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                if cmd == "connect":
                    port, baud = arg  # type: ignore[misc]
                    self._do_connect(port, baud)
                elif cmd == "disconnect":
                    self._do_disconnect()
                elif cmd == "send":
                    self._do_send(arg)  # type: ignore[arg-type]
                elif cmd == "rt":
                    self._do_send_realtime(arg)  # type: ignore[arg-type]
                elif cmd == "stream":
                    self._do_stream(arg)  # type: ignore[arg-type]
                elif cmd == "stop_job":
                    self._do_stop_job()
                elif cmd == "quit":
                    return
            except Exception as exc:  # noqa: BLE001 - surface anything
                self.errorOccurred.emit(f"{cmd}: {exc}")

    def _do_connect(self, port: str, baud: int) -> None:
        if self._serial is not None:
            self._do_disconnect()
        try:
            self._serial = self._serial_factory(port, baud)
            if hasattr(self._serial, "open") and not getattr(self._serial, "is_open", False):
                self._serial.open()  # type: ignore[attr-defined]
            self._pending_lengths.clear()
            self._inflight = 0
            # NOTA: emettiamo `connected` PRIMA di `bufferStateChanged` in
            # modo che la UI riceva per primo l'evento "sei connesso".
            self.connected.emit(port, baud)
            self._emit_buffer_state()
        except Exception as exc:  # noqa: BLE001
            self._serial = None
            self.errorOccurred.emit(f"Connect failed: {exc}")

    def _do_disconnect(self) -> None:
        if self._serial is None:
            return
        try:
            self._serial.close()
        except Exception:
            pass
        self._serial = None
        self._pending_lengths.clear()
        self._inflight = 0
        self._job_lines = []
        self._job_active = False
        self.disconnected.emit()
        self._emit_buffer_state()

    def _do_send(self, line: str) -> None:
        if self._serial is None or not getattr(self._serial, "is_open", False):
            self.errorOccurred.emit("Not connected")
            return
        payload = (line + "\n").encode("utf-8")
        self._serial.write(payload)  # type: ignore[attr-defined]
        self._pending_lengths.append(len(payload))
        self._inflight += len(payload)
        self._emit_buffer_state()

    def _do_send_realtime(self, byte: bytes) -> None:
        if self._serial is None or not getattr(self._serial, "is_open", False):
            self.errorOccurred.emit("Not connected")
            return
        self._serial.write(byte)  # type: ignore[attr-defined]

    def _do_stream(self, lines: list[str]) -> None:
        if self._serial is None or not getattr(self._serial, "is_open", False):
            self.errorOccurred.emit("Not connected")
            return
        clean = [ln.rstrip("\r\n") for ln in lines if ln.strip()]
        self._job_lines = clean
        self._job_total = len(clean)
        self._job_sent = 0
        self._job_active = True
        self.progressChanged.emit(0, self._job_total)
        self._try_send_job_lines()

    def _do_stop_job(self) -> None:
        was_active = self._job_active
        self._job_lines = []
        self._job_active = False
        try:
            self._do_send_realtime(b"\x18")
        except Exception:
            pass
        if was_active:
            self.jobFinished.emit(False)

    # ------------------------------------------------------------------
    # Internals: serial I/O
    # ------------------------------------------------------------------

    def _poll_serial(self) -> None:
        # Read up to a bounded number of lines per loop iteration so the
        # command queue still gets a chance to drain under heavy load.
        for _ in range(64):
            if self._serial is None:
                return
            try:
                raw = self._serial.readline()  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                self.errorOccurred.emit(f"Read failed: {exc}")
                self._do_disconnect()
                return
            if not raw:
                return
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if line:
                self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        self.lineReceived.emit(line)

        if line == "ok":
            self._ack_one()
            return

        err = grbl.parse_error(line)
        if err is not None:
            self._ack_one()
            self.errorResponse.emit(err)
            return

        alarm = grbl.parse_alarm(line)
        if alarm is not None:
            self.alarmReceived.emit(alarm)
            return

        status = grbl.parse_status(line)
        if status is not None:
            self.statusReceived.emit(status)
            return

        fb = grbl.parse_feedback(line)
        if fb is not None:
            self.messageReceived.emit(fb)
            return

        welcome = grbl.parse_welcome(line)
        if welcome is not None:
            self.messageReceived.emit(welcome)
            return

        # Fall back: settings and any other line become a "message"
        self.messageReceived.emit(line)

    def _ack_one(self) -> None:
        if self._pending_lengths:
            n = self._pending_lengths.popleft()
            self._inflight = max(0, self._inflight - n)
            self._emit_buffer_state()

    def _emit_buffer_state(self) -> None:
        """Notifica il cambio di stato del buffer (inflight, capienza)."""
        self.bufferStateChanged.emit(self._inflight, self.RX_BUFFER_SIZE)

    def _try_send_job_lines(self) -> None:
        if not self._job_active:
            return
        if self._serial is None or not getattr(self._serial, "is_open", False):
            return

        wrote_any = False
        while self._job_lines:
            next_line = self._job_lines[0]
            payload_len = len(next_line.encode("utf-8")) + 1
            if self._inflight + payload_len > self.RX_BUFFER_SIZE:
                break
            self._job_lines.pop(0)
            try:
                self._serial.write((next_line + "\n").encode("utf-8"))  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                self.errorOccurred.emit(f"Write failed: {exc}")
                self._job_lines = []
                self._job_active = False
                self.jobFinished.emit(False)
                return
            self._pending_lengths.append(payload_len)
            self._inflight += payload_len
            self._job_sent += 1
            self.progressChanged.emit(self._job_sent, self._job_total)
            wrote_any = True

        if wrote_any:
            self._emit_buffer_state()

        if not self._job_lines and self._inflight == 0:
            self._job_active = False
            self.jobFinished.emit(True)