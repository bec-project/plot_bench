from types import SimpleNamespace

from plotbench import host
from plotbench.campaign import hardware_summary


def test_linux_metadata_uses_nonidentifying_hardware_fields(monkeypatch):
    monkeypatch.setattr(
        host.platform,
        "freedesktop_os_release",
        lambda: {"NAME": "Example Linux", "VERSION_ID": "9"},
    )
    monkeypatch.setattr(host.platform, "release", lambda: "6.0-test")
    monkeypatch.setattr(
        host,
        "Path",
        lambda path: SimpleNamespace(
            read_text=lambda: "model name : Example CPU\nserial : private-value\n"
        ),
    )
    monkeypatch.setattr(
        host,
        "command_output",
        lambda args: '00:02.0 "VGA compatible controller" "Example vendor" "GPU model"\n00:03.0 "Ethernet controller" "Vendor" "Network"',
    )
    data = host.linux_metadata()
    assert data["cpu_model"] == "Example CPU"
    assert data["graphics"] == [{"model": "GPU model", "vendor": "Example vendor"}]
    assert "private-value" not in str(data)
    assert "00:02.0" not in str(data)
    summary = hardware_summary(data, origin="test")
    assert summary["os"] == "Example Linux 9 (6.0-test)"
    assert summary["graphics"][0]["model"] == "GPU model"


def test_linux_missing_hardware_stays_missing(monkeypatch):
    def unavailable(*args):
        raise OSError("unavailable")

    monkeypatch.setattr(host.platform, "freedesktop_os_release", unavailable)
    monkeypatch.setattr(host, "Path", lambda path: SimpleNamespace(read_text=unavailable))
    monkeypatch.setattr(host, "command_output", lambda args: None)
    data = host.linux_metadata()
    assert data["cpu_model"] is None
    assert data["graphics"] == []
    assert data["os"]["name"] == "Linux"
