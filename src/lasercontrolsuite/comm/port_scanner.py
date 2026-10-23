"""Enumerate available serial ports. Never raises."""
from __future__ import annotations


def list_serial_ports() -> list[dict]:
    """Return a list of ``{"device", "description", "hwid"}`` dicts.

    Empty list if pyserial is unavailable or no ports are present.
    Any underlying error is swallowed: this function is UI-facing and must
    never crash the app just because a port enumeration failed.
    """
    try:
        from serial.tools import list_ports  # type: ignore
    except Exception:
        return []

    out: list[dict] = []
    try:
        for p in list_ports.comports():
            out.append({
                "device": getattr(p, "device", "") or "",
                "description": getattr(p, "description", "") or "",
                "hwid": getattr(p, "hwid", "") or "",
            })
    except Exception:
        return out
    return out