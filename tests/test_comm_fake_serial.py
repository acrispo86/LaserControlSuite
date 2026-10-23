import pytest

from lasercontrolsuite.comm.fake_serial import FakeSerialPort


def test_open_close_state():
    s = FakeSerialPort()
    assert not s.is_open
    s.open()
    assert s.is_open
    s.close()
    assert not s.is_open


def test_write_fails_when_closed():
    s = FakeSerialPort()
    with pytest.raises(OSError):
        s.write(b"G0X0\n")


def test_auto_ok_one_per_newline():
    s = FakeSerialPort()
    s.open()
    s.write(b"G0X0\n")
    s.write(b"G1X1\nG1Y1\n")
    # 3 lines total -> 3 oks
    lines = []
    while True:
        l = s.readline()
        if not l:
            break
        lines.append(l.strip())
    assert lines == [b"ok", b"ok", b"ok"]


def test_no_auto_ok_when_disabled():
    s = FakeSerialPort(auto_ok=False)
    s.open()
    s.write(b"G0X0\n")
    assert s.readline() == b""


def test_status_query_response():
    s = FakeSerialPort()
    s.open()
    s.status_response = "<Run|MPos:1,2,3>"
    s.write(b"?")
    assert s.readline().strip() == b"<Run|MPos:1,2,3>"


def test_status_query_default_response():
    s = FakeSerialPort()
    s.open()
    s.write(b"?")
    resp = s.readline().strip()
    assert resp.startswith(b"<Idle")


def test_realtime_bytes_have_no_response():
    s = FakeSerialPort()
    s.open()
    s.write(b"!")
    s.write(b"~")
    s.write(b"\x18")
    assert s.readline() == b""


def test_push_response_and_read():
    s = FakeSerialPort()
    s.open()
    s.push_response("hello")
    assert s.readline() == b"hello\r\n"


def test_sent_lines_helper():
    s = FakeSerialPort()
    s.open()
    s.write(b"G0X0\n")
    s.write(b"G1X1\n")
    assert s.sent_lines() == ["G0X0", "G1X1"]
    s.clear_tx()
    assert s.sent_lines() == []


def test_read_returns_partial_data():
    s = FakeSerialPort()
    s.open()
    s.push_response("abcdef")
    assert s.read(3) == b"abc"
    assert s.read(100) == b"def\r\n"