"""Source implementations share configuration and transport contracts."""

import json
import os
from pathlib import Path

BACKENDS = ("python", "rust")
DEFAULT_BACKEND = "rust"
ROOT = Path(__file__).resolve().parents[3]


def validate_backend(backend):
    if backend not in BACKENDS:
        raise ValueError(f"backend must be one of {BACKENDS}")
    return backend


def backend_from_health(health):
    return validate_backend(health.get("backend", "python"))


def rust_source_command(config, output, host, port):
    executable = ROOT / "backends/rust/target/release/plotbench-source-rust"
    if not executable.is_file():
        raise FileNotFoundError(f"{executable} is missing; run ./scripts/setup rust")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / "source-config.json"
    config_path.write_text(json.dumps(config.to_dict(), indent=2, allow_nan=False) + "\n")
    return [
        str(executable),
        "--host",
        host,
        "--port",
        str(port),
        "--config",
        str(config_path),
        "--output",
        str(output),
        "--controls",
        str(Path(__file__).with_name("controls.html")),
    ]


def launch_rust_source(config, output, host, port):
    command = rust_source_command(config, output, host, port)
    os.execv(command[0], command)
