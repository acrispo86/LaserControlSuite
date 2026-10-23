"""Integration tests for GrblController with FakeSerialPort.

Note: pytest-qt provides ``qtbot`` and requires a QApplication.
"""
import time

import pytest

from lasercontrolsuite.comm.controller import GrblController
from lasercontrolsuite.comm.fake_serial import FakeSerialPort


@pytest.fixture
def controller_factory(qapp):
    created = []

    def factory(auto_ok: bool = True):
        fake = FakeSerialPort(auto_ok=auto_ok)
        ctrl = GrblController(serial_factory=lambda port, baud: fake)
        ctrl.start()
        created.append((ctrl, fake))
        return ctrl, fake

    yield factory

    for ctrl, _fake in created:
        ctrl.shutdown()
        ctrl.wait(2000)


def test_connect_emits_connected(controller_factory, qtbot):
    ctrl, fake = controller_factory()
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    assert fake.is_open


def test_disconnect_emits_disconnected(controller_factory, qtbot):
    ctrl, fake = controller_factory()
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    with qtbot.waitSignal(ctrl.disconnected, timeout=2000):
        ctrl.disconnect_port()
    assert not fake.is_open


def test_send_line_reaches_serial(controller_factory, qtbot):
    ctrl, fake = controller_factory()
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    ctrl.send_line("$H")
    # Poll for up to 1s for the line to appear
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if "$H" in fake.sent_lines():
            break
        qtbot.wait(20)
    assert "$H" in fake.sent_lines()


def test_status_received_signal(controller_factory, qtbot):
    ctrl, fake = controller_factory()
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    fake.status_response = "<Run|MPos:3.000,4.000,0.000|FS:100,0>"
    with qtbot.waitSignal(ctrl.statusReceived, timeout=2000) as blocker:
        ctrl.status_query()
    st = blocker.args[0]
    assert st["state"] == "Run"
    assert st["mpos"] == (3.0, 4.0, 0.0)


def test_error_response_signal(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=False)
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    fake.push_response("error:9")
    ctrl.send_line("G0X0")
    with qtbot.waitSignal(ctrl.errorResponse, timeout=2000) as blocker:
        # The "error:9" is already in the buffer; triggering a read cycle
        # by sending another harmless line is enough.
        ctrl.send_line("?")
    assert blocker.args[0] == 9


def test_alarm_signal(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=False)
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    with qtbot.waitSignal(ctrl.alarmReceived, timeout=2000) as blocker:
        fake.push_response("ALARM:1")
    assert blocker.args[0] == 1


def test_message_received_for_feedback(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=False)
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    with qtbot.waitSignal(ctrl.messageReceived, timeout=2000) as blocker:
        fake.push_response("[MSG:Reset to continue]")
    assert "Reset" in blocker.args[0]


def test_welcome_banner_emits_message(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=False)
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    with qtbot.waitSignal(ctrl.messageReceived, timeout=2000) as blocker:
        fake.push_response("Grbl 1.1h ['$' for help]")
    assert blocker.args[0].startswith("Grbl")


def test_jog_command_format(controller_factory, qtbot):
    ctrl, fake = controller_factory()
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    ctrl.jog(1.5, -2.5, feed=500)
    deadline = time.time() + 1.0
    found = None
    while time.time() < deadline:
        for line in fake.sent_lines():
            if line.startswith("$J="):
                found = line
                break
        if found:
            break
        qtbot.wait(20)
    assert found == "$J=G91G21X1.500Y-2.500F500"


def test_stream_gcode_completes(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=True)
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    lines = [f"G1 X{i} Y{i}" for i in range(20)]
    with qtbot.waitSignal(ctrl.jobFinished, timeout=5000) as blocker:
        ctrl.stream_gcode(lines)
    assert blocker.args[0] is True
    sent = fake.sent_lines()
    for ln in lines:
        assert ln in sent


def test_stream_progress_signals(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=True)
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    lines = [f"G1X{i}" for i in range(10)]
    progress = []
    ctrl.progressChanged.connect(lambda s, t: progress.append((s, t)))
    with qtbot.waitSignal(ctrl.jobFinished, timeout=5000):
        ctrl.stream_gcode(lines)
    assert progress[0] == (0, 10)
    assert progress[-1] == (10, 10)


def test_stop_job_aborts(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=False)
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    lines = [f"G1X{i}" for i in range(100)]
    with qtbot.waitSignal(ctrl.jobFinished, timeout=5000) as blocker:
        ctrl.stream_gcode(lines)
        qtbot.wait(50)
        ctrl.stop_job()
    assert blocker.args[0] is False
    # Soft reset byte must have been sent
    assert b"\x18" in fake.sent_bytes()


def test_send_without_connection_emits_error(controller_factory, qtbot):
    ctrl, _fake = controller_factory()
    with qtbot.waitSignal(ctrl.errorOccurred, timeout=2000) as blocker:
        ctrl.send_line("$H")
    assert "Not connected" in blocker.args[0]


def test_shutdown_terminates_thread(controller_factory):
    ctrl, _fake = controller_factory()
    ctrl.shutdown()
    assert ctrl.wait(2000) is True


# ---------------------------------------------------- Step 9b: buffer state


def test_buffer_state_emitted_on_send(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=False)
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    with qtbot.waitSignal(ctrl.bufferStateChanged, timeout=2000) as blocker:
        ctrl.send_line("G0X0")
    inflight, size = blocker.args
    assert size == GrblController.RX_BUFFER_SIZE
    assert inflight >= len("G0X0\n")  # almeno la lunghezza del payload


def test_buffer_state_decreases_on_ok(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=True)
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    states: list[tuple[int, int]] = []
    ctrl.bufferStateChanged.connect(lambda i, s: states.append((i, s)))
    ctrl.send_line("G0X0")
    # Attende che l'ack auto-ok svuoti il buffer
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if states and states[-1][0] == 0:
            break
        qtbot.wait(20)
    assert states[-1][0] == 0
    assert states[-1][1] == GrblController.RX_BUFFER_SIZE


def test_buffer_state_reset_on_connect(controller_factory, qtbot):
    ctrl, fake = controller_factory(auto_ok=False)
    states: list[tuple[int, int]] = []
    ctrl.bufferStateChanged.connect(lambda i, s: states.append((i, s)))
    with qtbot.waitSignal(ctrl.connected, timeout=2000):
        ctrl.connect_port("FAKE", 115200)
    assert (0, GrblController.RX_BUFFER_SIZE) in states