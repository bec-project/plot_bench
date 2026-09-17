"""Build the shared Fyne Go adapter for the browser with its matching Go runtime."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    go = shutil.which("go")
    if not go:
        raise SystemExit("Fyne WebAssembly requires Go 1.27+; see docs/setup.md.")
    source = ROOT / "frontends/fyne"
    environment = dict(
        os.environ,
        GOPATH=str(ROOT / ".cache/go"),
        GOMODCACHE=str(ROOT / ".cache/go/pkg/mod"),
        GOCACHE=str(ROOT / ".cache/go-build"),
        GOOS="js",
        GOARCH="wasm",
        CGO_ENABLED="0",
        GOEXPERIMENT=os.environ.get("GOEXPERIMENT", "simd"),
    )
    # Query inside the module so automatic toolchain selection matches the build.
    goroot = Path(
        subprocess.check_output(
            [go, "-C", str(source), "env", "GOROOT"], env=environment, text=True
        ).strip()
    )
    runtime = next(
        (
            path
            for path in (
                goroot / "lib/wasm/wasm_exec.js",
                goroot / "misc/wasm/wasm_exec.js",
            )
            if path.is_file()
        ),
        None,
    )
    if runtime is None:
        raise SystemExit(f"Go browser runtime wasm_exec.js not found in {goroot}")
    # Homebrew puts the distribution license beside libexec rather than inside it.
    go_license = next(
        (
            path
            for path in (goroot / "LICENSE", goroot.parent / "LICENSE")
            if path.is_file()
        ),
        None,
    )
    if go_license is None:
        raise SystemExit(
            f"Go distribution LICENSE not found in {goroot} or {goroot.parent}"
        )
    if not (HERE / "index.html").is_file():
        raise SystemExit(f"Browser entrypoint missing: {HERE / 'index.html'}")
    cache = ROOT / ".cache/fyne-wasm"
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as temporary:
        stage = Path(temporary) / "dist"
        stage.mkdir()
        subprocess.run(
            [
                go,
                "-C",
                str(source),
                "build",
                "-mod=readonly",
                "-trimpath",
                "-tags",
                "release,no_animations",
                "-o",
                str(stage / "plotbench-fyne.wasm"),
                ".",
            ],
            env=environment,
            check=True,
        )
        shutil.copy2(runtime, stage / "wasm_exec.js")
        shutil.copy2(go_license, stage / "LICENSE-go.txt")
        for asset in sorted(HERE.rglob("*")):
            relative = asset.relative_to(HERE)
            if {"dist", "tests", "node_modules"}.intersection(relative.parts):
                continue
            if asset.is_file() and asset.suffix in {".html", ".js", ".css"}:
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset, target)
        destination = HERE / "dist"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(stage), destination)
    print(
        "Built Fyne WebAssembly with the shared locked Go module and matching browser runtime"
    )


if __name__ == "__main__":
    main()
