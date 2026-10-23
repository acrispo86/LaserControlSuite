from lasercontrolsuite.comm.port_scanner import list_serial_ports


def test_list_serial_ports_returns_list():
    ports = list_serial_ports()
    assert isinstance(ports, list)
    for p in ports:
        assert set(p.keys()) == {"device", "description", "hwid"}
        assert isinstance(p["device"], str)