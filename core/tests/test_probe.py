import json
import re
from types import SimpleNamespace

import pytest

from plotbench.config import Config
from plotbench.generator import make_packet
from plotbench.probe import build_probe_report, receive_probe, summarize_probe, write_probe_report
from plotbench.report import read_jsonl
from plotbench.runner import source_process


def test_receiver_summary_distinguishes_generation_from_delivery():
    samples = [
        dict(seq=seq, measured=measured, bytes=1024, decode_ms=0.1, ack_ms=0.2, receive_age_ms=0.3)
        for seq, measured in ((0, False), (1, True), (3, True), (4, False))
    ]
    source = [
        dict(time_ms=value, generation_ms=2, mailbox_drops=1)
        for value in (900, 1000, 1100, 1200, 1300, 1400, 1500)
    ]
    result = summarize_probe(samples, source, 1000, 0.5, 10)
    assert result["source_hz"] == 10
    assert result["received_hz"] == 4
    assert result["target_met"] is False
    assert result["gap_percent"] == 100 / 3
    assert result["source_mailbox_drops"] == 5
    assert result["source_generation_p95_ms"] == 2


def test_common_receiver_decodes_and_acknowledges_real_python_source(tmp_path):
    config = Config(hz=60, points=32, append_count=4, width=8, height=8, view="image")
    folder = tmp_path / "source"
    with source_process(folder, config, backend="python") as url:
        samples, start = receive_probe(url, config, 0.05, 0.2)
    result = summarize_probe(samples, read_jsonl(folder / "source.jsonl"), start, 0.2, 60)
    assert result["received_frames"] > 0
    assert result["source_hz"] > 0
    assert result["received_hz"] > 0
    assert all(a["seq"] < b["seq"] for a, b in zip(samples, samples[1:], strict=False))


def test_failed_probe_is_retained_in_all_report_formats(tmp_path):
    rows = [
        dict(
            scenario="test",
            backend="rust",
            repetition=1,
            target_hz=120,
            status="failed",
            error="source unavailable",
            path="run-0001",
        )
    ]
    write_probe_report(tmp_path, rows)
    assert json.loads((tmp_path / "summary.json").read_text())["runs"] == rows
    assert "source unavailable" in (tmp_path / "summary.csv").read_text()
    assert "failed" in (tmp_path / "report.html").read_text()
    assert "No valid measurements" in (tmp_path / "report.html").read_text()
    assert "failed" in (tmp_path / "report-extended.html").read_text()
    assert "<table" not in (tmp_path / "report.html").read_text()
    assert not (tmp_path / "received-throughput.svg").exists()


def test_probe_report_regenerates_from_raw_manifests_and_keeps_evidence(tmp_path):
    folder = tmp_path / "run-0001"
    folder.mkdir()
    row = dict(
        scenario="waveform",
        backend="rust",
        repetition=1,
        target_hz=60,
        status="ok",
        config=Config(hz=60, view="waveform").to_dict(),
        measurement_seconds=10,
        source_hz=60,
        received_hz=58,
        target_met=False,
    )
    manifest = json.dumps(row)
    (folder / "run.json").write_text(manifest)
    (folder / "receiver.jsonl").write_text(' {"seq": 1}\n')
    (tmp_path / "summary.json").write_text('{"runs": []}')
    report = build_probe_report(tmp_path)
    result = json.loads((tmp_path / "summary.json").read_text())
    assert result["runs"] == [dict(row, path="run-0001")]
    assert len(result["comparisons"]) == 1
    assert (tmp_path / "received-throughput.svg").is_file()
    assert (tmp_path / "source-delivery.svg").is_file()
    compact = report.read_text()
    extended = report.with_name("report-extended.html").read_text()
    assert 'href="run-0001/run.json"' in extended
    assert "<table" not in compact and "<table" in extended
    assert 'href="report-extended.html#runs"' in compact
    assert 'href="report.html"' in extended
    assert re.findall(r"<svg.*?</svg>", compact, re.S) == re.findall(
        r"<svg.*?</svg>", extended, re.S
    )
    assert (folder / "run.json").read_text() == manifest
    assert (folder / "receiver.jsonl").read_text() == ' {"seq": 1}\n'
    single = build_probe_report(folder)
    assert 'href="./run.json"' in single.with_name("report-extended.html").read_text()
    assert (folder / "run.json").read_text() == manifest


def test_probe_regeneration_rejects_frontend_results_without_overwriting_report(tmp_path):
    (tmp_path / "run.json").write_text(
        json.dumps(
            dict(
                frontend="pyqtgraph",
                backend="rust",
                scenario="waveform",
                target_hz=60,
                repetition=1,
                status="ok",
            )
        )
    )
    report = tmp_path / "report.html"
    report.write_text("Existing frontend report")
    with pytest.raises(ValueError, match="not a receiver-probe"):
        build_probe_report(tmp_path)
    assert report.read_text() == "Existing frontend report"


def test_slow_source_is_allowed_until_fixed_measurement_end(monkeypatch):
    config = Config(hz=0.1, points=1, append_count=1, view="waveform")
    packets = [bytes(make_packet(config, seq)) for seq in (0, 1)]
    clock = SimpleNamespace(now=0.0)
    sent = []

    class Socket:
        next_frame = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def recv(self, timeout):
            arrival = self.next_frame * 10
            if self.next_frame < len(packets) and arrival <= clock.now + timeout:
                clock.now = float(arrival)
                packet = packets[self.next_frame]
                self.next_frame += 1
                return packet
            clock.now += timeout
            raise TimeoutError

        def send(self, message):
            sent.append(json.loads(message))

    monkeypatch.setattr("plotbench.probe.connect", lambda *a, **kw: Socket())
    monkeypatch.setattr(
        "plotbench.probe.time",
        SimpleNamespace(perf_counter=lambda: clock.now, time_ns=lambda: int(clock.now * 1e9)),
    )
    samples, start = receive_probe("http://localhost", config, 0, 11)
    assert [sample["seq"] for sample in samples] == [0, 1]
    assert all(sample["measured"] for sample in samples)
    assert clock.now == 11 and start == 0
    assert [message["ack"] for message in sent] == [0, 1]
