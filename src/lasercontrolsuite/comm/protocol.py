"""GRBL 1.1 protocol parsing utilities.

Pure Python: no Qt, no pyserial, no I/O. All functions are deterministic
and side-effect free so they can be unit-tested exhaustively.

Reference: https://github.com/gnea/grbl/wiki/Interfacing-with-Grbl
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# State / status report
# ---------------------------------------------------------------------------

KNOWN_STATES = frozenset({
    "Idle", "Run", "Hold", "Jog", "Alarm", "Door", "Check", "Home", "Sleep",
})


def parse_status(line: str) -> Optional[dict]:
    """Parse a ``<...>`` status report line.

    Returns a dict like::

        {"state": "Run", "substate": None,
         "mpos": (1.0, 2.0, 0.0), "wpos": None, "wco": None,
         "feed": 500.0, "speed": 0.0, "ov": (100, 100, 100),
         "pins": "XYZ", "raw": "<...>"}

    Returns ``None`` if ``line`` is not a status report.
    """
    line = line.strip()
    if len(line) < 2 or not (line.startswith("<") and line.endswith(">")):
        return None
    body = line[1:-1]
    parts = body.split("|")
    if not parts or not parts[0]:
        return None

    first = parts[0]
    if ":" in first:
        state, sub_raw = first.split(":", 1)
        try:
            substate: Optional[int] = int(sub_raw)
        except ValueError:
            substate = None
    else:
        state, substate = first, None

    result: dict = {
        "state": state,
        "substate": substate,
        "raw": line,
    }

    for p in parts[1:]:
        if ":" not in p:
            continue
        key, val = p.split(":", 1)
        if key in ("MPos", "WPos", "WCO"):
            try:
                result[key.lower()] = tuple(float(x) for x in val.split(","))
            except ValueError:
                continue
        elif key == "FS":
            try:
                f_str, s_str = val.split(",", 1)
                result["feed"] = float(f_str)
                result["speed"] = float(s_str)
            except (ValueError, TypeError):
                pass
        elif key == "F":
            try:
                result["feed"] = float(val)
            except ValueError:
                pass
        elif key == "Ov":
            try:
                result["ov"] = tuple(int(x) for x in val.split(","))
            except (ValueError, TypeError):
                pass
        elif key == "Pn":
            result["pins"] = val
        elif key == "A":
            result["accessories"] = val
        elif key == "Bf":
            result["buffer"] = val
        elif key == "Ln":
            result["line_number"] = val
    return result


# ---------------------------------------------------------------------------
# Errors / alarms
# ---------------------------------------------------------------------------

def parse_error(line: str) -> Optional[int]:
    """Parse ``error:N`` (may have trailing text). Returns ``None`` otherwise."""
    line = line.strip()
    if not line.startswith("error:"):
        return None
    try:
        return int(line[6:].split()[0])
    except (ValueError, IndexError):
        return None


def parse_alarm(line: str) -> Optional[int]:
    """Parse ``ALARM:N``. Returns ``None`` otherwise."""
    line = line.strip()
    if not line.startswith("ALARM:"):
        return None
    try:
        return int(line[6:].split()[0])
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# $ settings, [MSG:...], welcome banner
# ---------------------------------------------------------------------------

def parse_setting(line: str) -> Optional[tuple[int, str]]:
    """Parse ``$N=value`` into ``(N, value_string)``. ``None`` otherwise."""
    line = line.strip()
    if not line.startswith("$") or "=" not in line:
        return None
    try:
        idx, value = line[1:].split("=", 1)
        return int(idx), value
    except ValueError:
        return None


def parse_feedback(line: str) -> Optional[str]:
    """Parse ``[TAG:...]`` / ``[MSG:...]`` / ``[VER:...]``.

    Returns the text *inside* brackets, or ``None``.
    """
    line = line.strip()
    if not (line.startswith("[") and line.endswith("]")):
        return None
    return line[1:-1]


def parse_welcome(line: str) -> Optional[str]:
    """Return ``line`` if it looks like the GRBL welcome banner."""
    line = line.strip()
    if line.startswith("Grbl "):
        return line
    return None


# ---------------------------------------------------------------------------
# Human-readable messages
# ---------------------------------------------------------------------------

ERROR_MESSAGES = {
    1:  "G-code letter not recognized",
    2:  "Numeric value format is not valid or missing",
    3:  "Dollar sign '$' command not recognized",
    4:  "Negative value not allowed",
    5:  "Homing is not enabled",
    6:  "Step pulse minimum time too short",
    7:  "EEPROM read fail; restore defaults",
    8:  "$ command used while machine is running",
    9:  "G-code locked (machine must be in Idle)",
    10: "Soft limits error: command not allowed",
    11: "Line overflow (max 255 chars)",
    12: "Step rate too high",
    13: "Safety door detected",
    14: "Startup line error",
    15: "Jog target exceeds machine travel",
    16: "Jog command missing G91 or G21",
    17: "Laser mode requires PWM output",
    20: "Unsupported or invalid G-code command",
    21: "Multiple G-code commands share the same modal group",
    22: "Feed rate not set or undefined",
    23: "G-code command value is not an integer",
    24: "Two G-code commands require the same axis word",
    25: "Repeated G-code word in same block",
    26: "No axis words in a G-code block requiring them",
    27: "Line number value out of range",
    28: "Value missing in a G-code block",
    29: "G-code value out of range",
    30: "G-code value is not a valid float",
    31: "G-code block contains no value",
    32: "G-code value is negative",
    33: "Motion target is invalid",
    34: "Linear motion without feed rate",
    35: "Arc radius value is invalid",
    36: "Unused value in arc command",
    37: "G-code motion command without axis words",
    38: "Number of G-code commands exceeds 4 modals",
}

ALARM_MESSAGES = {
    1: "Hard limit triggered",
    2: "Soft limit alarm",
    3: "Reset while in motion (position lost)",
    4: "Probe fail (initial)",
    5: "Probe fail (contact not established)",
    6: "Homing fail (reset during cycle)",
    7: "Homing fail (door opened)",
    8: "Homing fail (pull off failed)",
    9: "Homing fail (approach did not clear limit switch)",
}


def describe_error(code: int) -> str:
    return ERROR_MESSAGES.get(code, f"Unknown error {code}")


def describe_alarm(code: int) -> str:
    return ALARM_MESSAGES.get(code, f"Unknown alarm {code}")