"""Campaign manifests: timezone-aware acquisition interval, host snapshot, completion state."""

import itertools
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from .host import host_snapshot

NOT_RECORDED = "Not recorded"


def local_now():
    return datetime.now().astimezone()


def timezone_record(moment):
    offset = moment.utcoffset()
    if offset is None:
        return None
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    hours, minutes = divmod(abs(total) // 60, 60)
    return dict(name=moment.tzname(), utc_offset=f"{sign}{hours:02d}:{minutes:02d}")


def planned_jobs(cases, modes, repetitions, frontends, backends):
    return [
        dict(
            scenario=case["name"], mode=mode, repetition=rep + 1, frontend=frontend, backend=backend
        )
        for case, mode, rep, frontend, backend in itertools.product(
            cases, modes, range(repetitions), frontends, backends
        )
    ]


def write_campaign_manifest(output, *, jobs, host=None, **fields):
    """Record acquisition start, timezone and hardware once, before any measured run."""
    started = local_now()
    record = dict(
        fields,
        started_at=started.isoformat(),
        started_at_utc=started.astimezone(UTC).isoformat(),
        timezone=timezone_record(started),
        completed_at=None,
        completed_at_utc=None,
        completion_status="running",
        runs_planned=len(jobs),
        runs_attempted=0,
        runs_failed=0,
        planned_jobs=jobs,
        host=host_snapshot() if host is None else host,
    )
    path = Path(output) / "suite.json"
    path.write_text(json.dumps(record, indent=2) + "\n")
    return record


def finalize_campaign_manifest(output, *, status, attempted, failed):
    path = Path(output) / "suite.json"
    record = json.loads(path.read_text())
    finished = local_now()
    record.update(
        completed_at=finished.isoformat(),
        completed_at_utc=finished.astimezone(UTC).isoformat(),
        completion_status=status,
        runs_attempted=attempted,
        runs_failed=failed,
    )
    path.write_text(json.dumps(record, indent=2) + "\n")
    return record


def parse_timestamp(value):
    """Return (datetime or None, note). Naive legacy strings never receive a timezone."""
    if value is None:
        return None, NOT_RECORDED
    if isinstance(value, (int, float)) and math.isfinite(value):
        return datetime.fromtimestamp(value / 1000, UTC), "UTC epoch milliseconds"
    if not isinstance(value, str):
        return None, "unreadable"
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None, f"unreadable: {value}"
    if moment.tzinfo is None:
        return None, f"{value} (timezone not recorded)"
    return moment, None


def describe_moment(moment, note=None):
    if moment is None:
        return note or NOT_RECORDED
    local = moment.isoformat(timespec="seconds")
    utc = moment.astimezone(UTC).isoformat(timespec="seconds")
    return local if local == utc else f"{local} ({utc})"


def _first(*values):
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def hardware_summary(host, *, origin):
    """Normalize a campaign or legacy source host record for display. Missing stays missing."""
    host = host if isinstance(host, dict) else {}
    os_record = host.get("os") if isinstance(host.get("os"), dict) else {}
    platform_text = host.get("platform")
    os_version = _first(os_record.get("version"))
    if os_version is None and isinstance(platform_text, str) and platform_text.startswith("macOS-"):
        os_version = platform_text.split("-")[1]
    os_label = os_record.get("name")
    if os_version:
        legacy_macos = isinstance(platform_text, str) and platform_text.startswith("macOS-")
        os_label = f"{os_record.get('name') or ('macOS' if legacy_macos else 'OS')} {os_version}"
        if os_record.get("build"):
            os_label += f" ({os_record['build']})"
    memory = host.get("memory_bytes")
    displays = []
    for display in host.get("displays") or []:
        if not isinstance(display, dict):
            continue
        displays.append(
            dict(
                name=display.get("_name"),
                pixels=display.get("_spdisplays_pixels"),
                configured=_first(
                    display.get("_spdisplays_resolution"), display.get("spdisplays_resolution")
                ),
                refresh=display.get("spdisplays_refresh_rate"),
                scaling=display.get("spdisplays_pixelresolution"),
                connection=display.get("spdisplays_connection_type"),
                kind=display.get("spdisplays_display_type"),
                main=display.get("spdisplays_main") == "spdisplays_yes",
                online=display.get("spdisplays_online"),
                mirror=display.get("spdisplays_mirror"),
            )
        )
    graphics = []
    for gpu in host.get("graphics") or []:
        if not isinstance(gpu, dict):
            continue
        graphics.append(
            dict(
                model=_first(gpu.get("model"), gpu.get("sppci_model")),
                vendor=_first(gpu.get("vendor"), gpu.get("spdisplays_vendor")),
                cores=gpu.get("sppci_cores"),
                metal=_first(
                    gpu.get("spdisplays_mtlgpufamilysupport"), gpu.get("spdisplays_metal")
                ),
            )
        )
    recorded, note = parse_timestamp(_first(host.get("recorded_at"), host.get("recorded_at_ms")))
    return dict(
        origin=origin,
        recorded_at=describe_moment(recorded, note),
        model_identifier=host.get("model_identifier"),
        cpu_model=host.get("cpu_model"),
        physical_cpus=host.get("physical_cpus"),
        logical_cpus=host.get("logical_cpus"),
        memory_gib=(memory / 1024**3) if isinstance(memory, (int, float)) else None,
        architecture=host.get("machine"),
        os=os_label,
        platform=platform_text,
        graphics=graphics,
        displays=displays,
        main_display=next((display for display in displays if display["main"]), None),
        display_metadata_error=host.get("display_metadata_error"),
    )


def read_campaign(path):
    """Read a result directory's campaign manifest; absent or legacy fields stay explicit."""
    path = Path(path)
    manifest_path = path / "suite.json"
    campaign = dict(
        manifest_present=manifest_path.exists(),
        started_at=NOT_RECORDED,
        completed_at=NOT_RECORDED,
        timezone=NOT_RECORDED,
        completion_status=NOT_RECORDED,
        runs_planned=None,
        runs_attempted=None,
        runs_failed=None,
        planned_jobs=None,
        display_context=None,
        backends=None,
        frontends=None,
        modes=None,
        repetitions=None,
        warmup_seconds=None,
        measurement_seconds=None,
        cooldown_seconds=None,
        suite_name=None,
        cases=None,
        hardware=None,
        argv=None,
        provenance=None,
        headless=None,
    )
    if not manifest_path.exists():
        return campaign
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        campaign["manifest_error"] = f"suite.json unreadable: {exc}"
        return campaign
    if not isinstance(manifest, dict):
        campaign["manifest_error"] = "suite.json is not an object"
        return campaign
    started, started_note = parse_timestamp(manifest.get("started_at"))
    completed, completed_note = parse_timestamp(manifest.get("completed_at"))
    timezone = manifest.get("timezone")
    if isinstance(timezone, dict):
        timezone_label = f"{timezone.get('name') or '?'} (UTC{timezone.get('utc_offset') or '?'})"
    elif started is not None and started.tzinfo is not None:
        timezone_label = f"UTC{started.strftime('%z')[:3]}:{started.strftime('%z')[3:]}"
    else:
        timezone_label = NOT_RECORDED
    suite = manifest.get("suite") if isinstance(manifest.get("suite"), dict) else {}
    frontends = manifest.get("selected_frontends") or suite.get("frontends")
    modes = manifest.get("selected_modes") or suite.get("modes")
    backends = (
        manifest.get("selected_backends")
        or suite.get("backends")
        or (["python"] if suite else None)
    )
    repetitions = manifest.get("repetitions", suite.get("repetitions"))
    cases = None
    if suite:
        try:
            from .runner import expand_cases

            cases = expand_cases(suite)
        except (ValueError, KeyError, TypeError):
            cases = None
    jobs = manifest.get("planned_jobs")
    if not isinstance(jobs, list):
        jobs = None
        if cases and frontends and modes and backends and isinstance(repetitions, int):
            jobs = planned_jobs(cases, modes, repetitions, frontends, backends)
    campaign.update(
        started_at=describe_moment(started, started_note),
        completed_at=describe_moment(completed, completed_note),
        started_moment=started,
        completed_moment=completed,
        timezone=timezone_label,
        completion_status=manifest.get("completion_status") or NOT_RECORDED,
        runs_planned=manifest.get("runs_planned", len(jobs) if jobs else None),
        runs_attempted=manifest.get("runs_attempted"),
        runs_failed=manifest.get("runs_failed"),
        planned_jobs=jobs,
        display_context=(
            (manifest.get("provenance") or {}).get("display_context")
            if isinstance(manifest.get("provenance"), dict)
            else None
        ),
        backends=backends,
        frontends=frontends,
        modes=modes,
        repetitions=repetitions,
        warmup_seconds=manifest.get("warmup_seconds", suite.get("warmup_seconds")),
        measurement_seconds=manifest.get("measurement_seconds", suite.get("measurement_seconds")),
        cooldown_seconds=suite.get("cooldown_seconds"),
        suite_name=suite.get("name"),
        cases=cases,
        hardware=(
            hardware_summary(manifest["host"], origin="campaign host snapshot in suite.json")
            if isinstance(manifest.get("host"), dict)
            else None
        ),
        argv=manifest.get("argv"),
        provenance=manifest.get("provenance"),
        headless=manifest.get("headless"),
    )
    return campaign


def legacy_hardware(folders):
    """Fall back to the first run's source host.json when no campaign snapshot exists."""
    for folder in folders:
        host_path = Path(folder) / "host.json"
        if not host_path.exists():
            continue
        try:
            host = json.loads(host_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(host, dict):
            backend = host.get("backend", "unknown")
            return hardware_summary(
                host, origin=f"{Path(folder).name}/host.json recorded by the {backend} source"
            )
    return None


def missing_jobs(jobs, rows):
    """Planned jobs with no recorded run manifest; never silently omitted from a report."""
    if not jobs:
        return None
    recorded = {
        (
            row["scenario"],
            row["mode"],
            row["frontend"],
            row.get("backend", "python"),
            row["repetition"],
        )
        for row in rows
    }
    return [
        job
        for job in jobs
        if (job["scenario"], job["mode"], job["frontend"], job["backend"], job["repetition"])
        not in recorded
    ]
