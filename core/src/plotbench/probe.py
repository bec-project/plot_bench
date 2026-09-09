"""A common decode-and-acknowledge receiver measures delivery without plotting."""

import csv
import itertools
import json
import math
import random
import time
from datetime import datetime
from html import escape
from pathlib import Path

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .backends import backend_from_health, validate_backend
from .campaign import finalize_campaign_manifest, local_now, read_campaign, write_campaign_manifest
from .client import request
from .config import Config
from .probe_charts import build_probe_charts
from .protocol import MAX_PACKET, decode_frame
from .provenance import capture_provenance, require_current_artifact
from .report import deadline_counter_increase, percentile, read_jsonl
from .runner import ROOT, expand_cases, source_process


def receive_probe(url, config, warmup, duration):
    """Decode every delivered packet and ACK immediately, with no GUI or mailbox."""
    rows = []
    first = first_wall = previous = last_received = None
    ws_url = url.replace("http", "ws", 1) + "/ws"
    with connect(ws_url, max_size=MAX_PACKET, max_queue=1, compression=None) as socket:
        while True:
            now = time.perf_counter()
            remaining = None if first is None else first + warmup + duration - now
            if remaining is not None and remaining <= 0:
                break
            try:
                packet = socket.recv(timeout=5 if remaining is None else min(5, remaining))
            except TimeoutError:
                if first is not None and time.perf_counter() >= first + warmup + duration:
                    break
                if last_received is not None and time.perf_counter() - last_received < max(
                    5, 2 / config.hz
                ):
                    continue
                raise RuntimeError(
                    "source stopped delivering packets within its expected interval"
                ) from None
            received, received_wall = time.perf_counter(), time.time_ns() / 1e6
            last_received = received
            if not isinstance(packet, bytes):
                raise ValueError("source sent a nonbinary frame")
            started = time.perf_counter()
            frame = decode_frame(packet)
            decode_ms = (time.perf_counter() - started) * 1000
            if frame.header["config"] != config.to_dict():
                raise ValueError("source configuration changed during receiver probe")
            if previous is not None and frame.seq <= previous:
                raise ValueError("source delivered a duplicate or out-of-order frame")
            if first is None:
                first, first_wall = received, received_wall
            socket.send(json.dumps({"ack": frame.seq, "generation": frame.generation}))
            rows.append(
                dict(
                    seq=frame.seq,
                    generation=frame.generation,
                    time_ms=received_wall,
                    elapsed_seconds=received - first,
                    bytes=len(packet),
                    decode_ms=decode_ms,
                    receive_age_ms=received_wall - frame.header["emitted_at_ms"],
                    ack_ms=(time.perf_counter() - started) * 1000 - decode_ms,
                    measured=warmup <= received - first < warmup + duration,
                )
            )
            previous = frame.seq
    return rows, first_wall + warmup * 1000


def summarize_probe(samples, source, start_ms, duration, target_hz):
    measured = [sample for sample in samples if sample["measured"]]
    produced = [
        sample for sample in source if start_ms <= sample["time_ms"] < start_ms + duration * 1000
    ]
    received_hz = len(measured) / duration
    source_hz = len(produced) / duration
    seqs = [sample["seq"] for sample in measured]
    span = max(seqs) - min(seqs) + 1 if seqs else 0
    return dict(
        received_hz=received_hz,
        source_hz=source_hz,
        received_frames=len(measured),
        target_met=received_hz >= 0.98 * target_hz and source_hz >= 0.98 * target_hz,
        throughput_mib_s=sum(sample["bytes"] for sample in measured) / duration / 2**20,
        source_generation_p95_ms=percentile([sample["generation_ms"] for sample in produced], 95),
        decode_p95_ms=percentile([sample["decode_ms"] for sample in measured], 95),
        ack_p95_ms=percentile([sample["ack_ms"] for sample in measured], 95),
        receive_age_p95_ms=percentile([sample["receive_age_ms"] for sample in measured], 95),
        source_mailbox_drops=sum(sample.get("mailbox_drops", 0) for sample in produced),
        source_deadline_misses=deadline_counter_increase(produced),
        gap_percent=100 * (span - len(seqs)) / span if span else None,
    )


def write_probe_report(output, rows):
    charts = build_probe_charts(rows)
    campaign = read_campaign(output)
    generated_at = local_now()
    summary = dict(
        report_provenance=capture_provenance(),
        report_generated_at=generated_at.isoformat(),
        campaign={key: value for key, value in campaign.items() if not key.endswith("_moment")},
        measurement="One common Python binary-frame decoder and immediate ACK receiver; no plotting",
        comparisons=charts["comparisons"],
        limitations=[
            "Measures generation, packing, local transport and this receiver; other client runtimes can differ.",
            "Target met means source and receiver each reached 98% of the configured rate in this repetition.",
            "Short runs are diagnostics, not proof of sustained performance or physical display rate.",
        ],
        runs=rows,
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    fields = list(
        dict.fromkeys(
            key
            for row in rows
            for key in row
            if key not in ("config", "health", "provenance", "provenance_after")
        )
    )
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    figures = []
    for key, filename, caption in (
        (
            "received_svg",
            "received-throughput.svg",
            "Bars show the median decoded frame rate; whiskers show the observed minimum and "
            "maximum across repetitions, not confidence intervals. Compare each bar with its "
            "requested-rate marker. No plotting library is running.",
        ),
        (
            "delivery_svg",
            "source-delivery.svg",
            "Open circles show median source generation; filled squares show median delivery "
            "to the common receiver. A large separation reveals a delivery/receiver constraint. "
            "Small differences can come from frame counts at measurement-window boundaries.",
        ),
    ):
        svg = charts[key]
        export = output / filename
        if svg is None:
            export.unlink(missing_ok=True)
            continue
        export.write_text(svg)
        figures.append(
            f'<figure><div class="chart-scroll" tabindex="0" role="region" '
            f'aria-label="Scrollable {filename.removesuffix(".svg").replace("-", " ")} chart">{svg}</div>'
            f'<figcaption>{caption} <a href="{filename}" download>Download SVG</a>'
            "</figcaption></figure>"
        )
    charted = sum(group["valid"] for group in charts["comparisons"])
    overview = "".join(figures) or "<p>No valid measurements are available for the charts.</p>"
    hardware = campaign.get("hardware") or {}
    memory = hardware.get("memory_gib")
    acquisition = (
        f"Acquisition {escape(campaign['started_at'])} to {escape(campaign['completed_at'])}; "
        f"timezone {escape(campaign['timezone'])}; status {escape(campaign['completion_status'])}. "
        f"Hardware: {escape(str(hardware.get('model_identifier') or 'Not recorded'))}, "
        f"{escape(str(hardware.get('cpu_model') or 'Not recorded'))}, "
        f"{'Not recorded' if memory is None else f'{memory:.0f} GiB'}, "
        f"{escape(str(hardware.get('os') or 'Not recorded'))}. "
        f"Report generated {escape(generated_at.isoformat(timespec='seconds'))}."
    )

    def value(row, key):
        item = row.get(key)
        return "—" if item is None else f"{item:.2f}"

    body = []
    for row in rows:
        met = row.get("target_met")
        target_label = "—" if met is None else "Yes" if met else "No"
        body.append(
            f'<tr><td>{escape(row["scenario"])}</td><td>{escape(row["backend"])}</td>'
            f'<td>{row["repetition"]}</td><td>{escape(row["status"])}</td>'
            + "".join(
                f"<td>{value(row, key)}</td>"
                for key in (
                    "target_hz",
                    "source_hz",
                    "received_hz",
                    "throughput_mib_s",
                    "source_generation_p95_ms",
                    "decode_p95_ms",
                    "receive_age_p95_ms",
                )
            )
            + f'<td>{target_label}</td><td><a href="{escape(row["path"])}/run.json">Details</a></td></tr>'
        )
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Source backend comparison</title>
<style>
:root{{font:15px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#dce8ee;background:#0b141b;color-scheme:dark}}
*{{box-sizing:border-box}}body{{max-width:1280px;margin:auto;padding:40px 28px}}h1{{font-size:36px;letter-spacing:-1px;margin:10px 0 16px}}h2{{font-size:22px;margin:0 0 14px}}p,li,figcaption{{line-height:1.65;color:#9fb6c4}}a{{color:#64dccc;text-underline-offset:3px}}a:focus-visible{{outline:2px solid #64dccc;outline-offset:4px}}
.eyebrow{{color:#8fa7b6;font-size:11px;font-weight:700;letter-spacing:2px}}.intro{{max-width:1000px}}.overview-note{{border-left:3px solid #64dccc;padding:8px 16px;margin:26px 0}}section{{margin:24px 0}}figure{{margin:0 0 24px;background:#11202a;border:1px solid #273d4b;border-radius:6px;overflow:hidden}}figcaption{{padding:0 24px 20px;font-size:13px}}.chart-scroll,.table-scroll{{overflow:auto}}svg{{display:block;width:100%;min-width:900px;height:auto}}.table-scroll{{background:#11202a;border:1px solid #273d4b;border-radius:6px}}table{{border-collapse:collapse;width:100%;white-space:nowrap}}th,td{{padding:12px 10px;border-bottom:1px solid #273d4b;text-align:left;font-size:13px}}th{{color:#9fb6c4;font-size:12px}}.notes{{border-top:1px solid #273d4b;padding-top:24px}}@media(max-width:700px){{body{{padding:26px 16px}}h1{{font-size:29px}}figcaption{{padding:0 16px 16px}}}}@media print{{body{{max-width:none;padding:0}}figure{{break-inside:avoid}}svg{{min-width:0}}a{{text-decoration:none}}}}
</style></head><body>
<header><div class="eyebrow">PLOTBENCH / RECORDED BACKEND CAPACITY</div><h1>Source backend comparison</h1><p class="intro">{escape(summary["measurement"])}</p></header>
<p class="overview-note">{acquisition}</p>
<p class="overview-note">{charted} of {len(rows)} recorded runs included in the charts. Medians use only valid runs with matching workload configuration, backend, target and measurement duration. All attempts remain in the table below.</p>
<section aria-label="Graphical overview">{overview}</section>
<section><h2>Per-run measurements</h2>
<p>Each backend runs alone with identical configuration and the same receiving client. Source Hz counts produced packets; received Hz counts successfully decoded and acknowledged packets. Generation time includes packing and dispatch overhead. No renderer is involved.</p>
<div class="table-scroll"><table><thead><tr><th>Workload</th><th>Backend</th><th>Repeat</th><th>Status</th><th>Target Hz</th><th>Source Hz</th><th>Received Hz</th><th>MiB/s</th><th>Generation p95 ms</th><th>Decode p95 ms</th><th>Age p95 ms</th><th>Target met</th><th>Evidence</th></tr></thead><tbody>{"".join(body)}</tbody></table></div></section>
<section class="notes"><h2>Reading the overview</h2>
<p>Target met is evaluated for each repetition, using unrounded rates: both generation and delivery must reach at least 98% of the requested rate. A median near the target does not mean every repetition passed. The chart shows how many valid repetitions met that criterion.</p>
<ul>{"".join(f"<li>{escape(item)}</li>" for item in summary["limitations"])}</ul>
<p><a href="summary.csv">Download per-run CSV</a> · <a href="summary.json">Download runs and chart summaries as JSON</a></p></section></body></html>"""
    (output / "report.html").write_text(html)


def build_probe_report(path):
    """Regenerate figures and summaries from preserved receiver-probe run manifests."""
    path = Path(path).resolve()
    folders = (
        [path]
        if (path / "run.json").exists()
        else sorted(manifest.parent for manifest in path.glob("*/run.json"))
    )
    if not folders:
        raise ValueError(f"no receiver-probe run manifests in {path}")
    rows = []
    required = {"backend", "scenario", "target_hz", "repetition", "status"}
    for folder in folders:
        row = json.loads((folder / "run.json").read_text())
        if not isinstance(row, dict) or not required <= row.keys() or "frontend" in row:
            raise ValueError(f"{folder / 'run.json'} is not a receiver-probe run manifest")
        rows.append(dict(row, path=str(folder.relative_to(path))))
    write_probe_report(path, rows)
    return path / "report.html"


def run_probe_suite(args):
    suite = json.loads(args.suite.read_text())
    cases = expand_cases(suite)
    backends = args.backends or suite.get("backends", ["python", "rust"])
    if not backends or len(set(backends)) != len(backends):
        raise ValueError("choose at least one backend, without duplicates")
    for backend in backends:
        validate_backend(backend)
    warmup = args.warmup if args.warmup is not None else float(suite.get("warmup_seconds", 2))
    duration = (
        args.duration if args.duration is not None else float(suite.get("measurement_seconds", 10))
    )
    repetitions = (
        args.repetitions if args.repetitions is not None else int(suite.get("repetitions", 3))
    )
    cooldown = float(suite.get("cooldown_seconds", 0.5))
    if (
        not all(math.isfinite(value) for value in (warmup, duration, cooldown))
        or warmup < 0
        or duration <= 0
        or cooldown < 0
        or repetitions < 1
    ):
        raise ValueError("invalid repetition count or timing")
    jobs = list(itertools.product(cases, backends, range(repetitions)))
    random.Random(suite.get("order_seed", 42)).shuffle(jobs)
    print(
        f"{len(jobs)} receiver-only runs · {len(jobs) * (warmup + duration) / 60:.1f} minutes of sampling plus startup",
        flush=True,
    )
    if args.dry_run:
        for case, backend, repetition in jobs:
            print(f"{case['name']} / {backend} / repeat {repetition + 1}")
        return
    artifacts = {"rust": require_current_artifact("rust")} if "rust" in backends else {}
    provenance = dict(capture_provenance(), artifacts=artifacts)
    output = (
        args.output or ROOT / "results" / datetime.now().strftime("backend-probe-%Y%m%d-%H%M%S")
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "suite.json").exists():
        raise ValueError("output already contains a suite; choose a new directory")
    write_campaign_manifest(
        output,
        jobs=[
            dict(
                scenario=case["name"],
                mode="probe",
                repetition=repetition + 1,
                frontend=None,
                backend=backend,
            )
            for case, backend, repetition in jobs
        ],
        suite=suite,
        selected_backends=backends,
        warmup_seconds=warmup,
        measurement_seconds=duration,
        repetitions=repetitions,
        provenance=provenance,
    )
    rows = []
    completion = "completed"
    try:
        for number, (case, backend, repetition) in enumerate(jobs, 1):
            folder = output / f"run-{number:04d}"
            config = Config(**case["config"])
            row = dict(
                scenario=case["name"],
                backend=backend,
                repetition=repetition + 1,
                target_hz=config.hz,
                measurement_seconds=duration,
                config=config.to_dict(),
                status="starting",
                provenance=provenance,
                path=folder.name,
            )
            folder.mkdir()
            print(
                f"[{number}/{len(jobs)}] {backend} · {case['name']} · repeat {repetition + 1}",
                flush=True,
            )
            try:
                row["provenance"] = dict(
                    capture_provenance(),
                    artifacts=(
                        {"rust": require_current_artifact("rust")} if backend == "rust" else {}
                    ),
                )
                with source_process(folder, config, backend=backend) as url:
                    samples, start = receive_probe(url, config, warmup, duration)
                    with (folder / "receiver.jsonl").open("w") as stream:
                        for sample in samples:
                            stream.write(json.dumps(sample, allow_nan=False) + "\n")
                    row["health"] = json.loads(request(url + "/api/health"))
                    if (
                        backend_from_health(row["health"]) != backend
                        or row["health"]["status"] != "ok"
                    ):
                        raise RuntimeError("source health does not match the requested backend")
                row.update(
                    summarize_probe(
                        samples, read_jsonl(folder / "source.jsonl"), start, duration, config.hz
                    )
                )
                row["status"] = "ok" if row["received_frames"] else "no-measured-data"
                after = capture_provenance()
                row["provenance_after"] = after
                if after["source_sha256"] != row["provenance"]["source_sha256"]:
                    row.update(
                        status="provenance-changed", error="source files changed during the run"
                    )
                if (
                    backend == "rust"
                    and require_current_artifact("rust")["files"]
                    != row["provenance"]["artifacts"]["rust"]["files"]
                ):
                    row.update(
                        status="provenance-changed", error="Rust artifact changed during the run"
                    )
            except KeyboardInterrupt:
                row["status"] = "interrupted"
                raise
            except (OSError, RuntimeError, ValueError, WebSocketException) as exc:
                row.update(status="failed", error=str(exc))
            finally:
                (folder / "run.json").write_text(json.dumps(row, indent=2, allow_nan=False) + "\n")
                rows.append(row)
            time.sleep(cooldown)
    except KeyboardInterrupt:
        completion = "interrupted"
        raise
    except BaseException:
        completion = "error"
        raise
    finally:
        finalize_campaign_manifest(
            output,
            status=completion,
            attempted=len(rows),
            failed=sum(row["status"] != "ok" for row in rows),
        )
        write_probe_report(output, rows)
        print(f"Report: {output / 'report.html'}", flush=True)
    if any(row["status"] != "ok" for row in rows):
        raise RuntimeError("receiver probe contains failures; see report")
