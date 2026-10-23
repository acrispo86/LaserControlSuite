import pytest

from lasercontrolsuite.comm import protocol as grbl


def test_parse_status_idle_full():
    line = "<Idle|MPos:1.000,2.500,0.000|FS:0,0|Ov:100,100,100>"
    st = grbl.parse_status(line)
    assert st is not None
    assert st["state"] == "Idle"
    assert st["substate"] is None
    assert st["mpos"] == (1.0, 2.5, 0.0)
    assert st["feed"] == 0.0
    assert st["speed"] == 0.0
    assert st["ov"] == (100, 100, 100)


def test_parse_status_with_substate_and_wpos():
    line = "<Run:1|WPos:10.000,5.000,0.000|FS:500,1000>"
    st = grbl.parse_status(line)
    assert st["state"] == "Run"
    assert st["substate"] == 1
    assert st["wpos"] == (10.0, 5.0, 0.0)
    assert st["feed"] == 500.0
    assert st["speed"] == 1000.0


def test_parse_status_alarm_and_pins():
    st = grbl.parse_status("<Alarm|MPos:0,0,0|Pn:XYZ>")
    assert st["state"] == "Alarm"
    assert st["pins"] == "XYZ"


def test_parse_status_rejects_non_status():
    assert grbl.parse_status("ok") is None
    assert grbl.parse_status("<not ended") is None
    assert grbl.parse_status("") is None


def test_parse_status_tolerates_malformed_numbers():
    # Bad MPos should simply be missing, not crash
    st = grbl.parse_status("<Idle|MPos:foo,bar,baz|FS:0,0>")
    assert st is not None
    assert "mpos" not in st
    assert st["feed"] == 0.0


def test_parse_error():
    assert grbl.parse_error("error:9") == 9
    assert grbl.parse_error("error:20 extra text") == 20
    assert grbl.parse_error("error:") is None
    assert grbl.parse_error("ok") is None
    assert grbl.parse_error("ERROR:1") is None


def test_parse_alarm():
    assert grbl.parse_alarm("ALARM:1") == 1
    assert grbl.parse_alarm("ALARM:9") == 9
    assert grbl.parse_alarm("alarm:1") is None
    assert grbl.parse_alarm("error:1") is None


def test_parse_setting():
    assert grbl.parse_setting("$0=10") == (0, "10")
    assert grbl.parse_setting("$100=80.000") == (100, "80.000")
    assert grbl.parse_setting("$=x") is None
    assert grbl.parse_setting("$$") is None


def test_parse_feedback():
    assert grbl.parse_feedback("[MSG:Reset to continue]") == "MSG:Reset to continue"
    assert grbl.parse_feedback("[VER:1.1h.20190825:]") == "VER:1.1h.20190825:"
    assert grbl.parse_feedback("msg without brackets") is None


def test_parse_welcome():
    assert grbl.parse_welcome("Grbl 1.1h ['$' for help]") is not None
    assert grbl.parse_welcome("GrblHAL 1.1") is None  # not the expected prefix
    assert grbl.parse_welcome("ok") is None


def test_describe_error_and_alarm_known():
    assert "Hom" in grbl.describe_error(5)
    assert "Hard limit" in grbl.describe_alarm(1)


def test_describe_error_unknown():
    assert grbl.describe_error(999).startswith("Unknown")
    assert grbl.describe_alarm(999).startswith("Unknown")