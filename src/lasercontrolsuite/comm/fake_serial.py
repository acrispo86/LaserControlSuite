"""In-memory serial port used for testing the GRBL controller.

Simulates a serial port that speaks enough GRBL to exercise the streaming
logic: every newline-terminated command is auto-acked with ``ok`` unless
``auto_ok`` is False, and ``?`` produces a status report.
"""
from __future__ import annotations

import threading
from typing import Optional


_DEFAULT_STATUS = "<Idle|MPos:0.000,0.000,0.000|FS:0,0>"


class FakeSerialPort:
    """Thread-safe, in-memory serial port.

    Attributes
    ----------
    auto_ok:
        When True (default) each written line receives an ``ok``.
    status_response:
        String returned for a ``?`` query (without CRLF). If None, a default
        idle report is returned.
    """

    def __init__(self, auto_ok: bool = True) -> None:
        self._open = False
        self._rx = bytearray()
        self._tx_log: list[bytes] = []
        self._lock = threading.Lock()
        self.auto_ok = auto_ok
        self.status_response: Optional[str] = None

    # ---- pyserial-like surface ----

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def in_waiting(self) -> int:
        with self._lock:
            return len(self._rx)

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def write(self, data: bytes) -> int:
        if not self._open:
            raise OSError("FakeSerialPort is not open")
        data = bytes(data)
        with self._lock:
            self._tx_log.append(data)
            if not self.auto_ok:
                return len(data)
            if data == b"?":
                resp = self.status_response or _DEFAULT_STATUS
                self._rx.extend(resp.encode("ascii", "replace") + b"\r\n")
                return len(data)
            # Realtime single-byte commands: no response.
            if len(data) == 1 and data[0] < 0x20 and data not in (b"\n", b"\r"):
                return len(data)
            # Ordinary commands: one "ok" per newline.
            for _ in range(data.count(b"\n")):
                self._rx.extend(b"ok\r\n")
        return len(data)

    def readline(self) -> bytes:
        with self._lock:
            idx = self._rx.find(b"\n")
            if idx < 0:
                return b""
            line = bytes(self._rx[: idx + 1])
            del self._rx[: idx + 1]
            return line

    def read(self, size: int = 1) -> bytes:
        with self._lock:
            n = min(size, len(self._rx))
            data = bytes(self._rx[:n])
            del self._rx[:n]
            return data

    def reset_input_buffer(self) -> None:
        with self._lock:
            self._rx.clear()

    # ---- test helpers ----

    def push_response(self, line: str) -> None:
        """Enqueue an incoming line, terminating with CRLF if needed."""
        if not line.endswith("\n"):
            line += "\r\n"
        with self._lock:
            self._rx.extend(line.encode("utf-8", "replace"))

    def sent_lines(self) -> list[str]:
        """Return every write so far, decoded and stripped (one per write)."""
        with self._lock:
            return [b.decode("utf-8", "replace").strip() for b in self._tx_log]

    def sent_bytes(self) -> list[bytes]:
        with self._lock:
            return list(self._tx_log)

    def clear_tx(self) -> None:
        with self._lock:
            self._tx_log.clear()