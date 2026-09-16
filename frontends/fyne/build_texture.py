"""Build the pinned Fyne dependency with an isolated local fork and recorded source overrides."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontends/fyne"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stock", action="store_true", help="build unmodified Fyne for comparison"
    )
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    env = os.environ.copy()
    env.setdefault("GOPATH", str(ROOT / ".cache/go"))
    env.setdefault("GOCACHE", str(ROOT / ".cache/go-build"))
    module = json.loads(
        subprocess.check_output(
            ["go", "list", "-m", "-json", "fyne.io/fyne/v2"], cwd=FRONTEND, env=env
        )
    )
    if module["Version"] != "v2.8.1" or "Replace" in module:
        raise SystemExit("Texture overlay requires unmodified Fyne v2.8.1")
    source = Path(module["Dir"])
    expected = json.loads(
        (FRONTEND / "_texture_overlay/upstream-sha256.json").read_text()
    )
    for relative, digest in expected.items():
        original = source / relative
        actual = (
            hashlib.sha256(original.read_bytes()).hexdigest()
            if original.exists()
            else None
        )
        if actual != digest:
            raise SystemExit(
                "Upstream source differs from the validated patch base: " + relative
            )
    replacements = {
        str(source / p.relative_to(FRONTEND / "_texture_overlay")): str(p)
        for p in sorted((FRONTEND / "_texture_overlay").rglob("*.go"))
    }
    build = FRONTEND / "build"
    build.mkdir(exist_ok=True)
    fork = ROOT / ".cache/fyne-texture-reuse"
    if not fork.exists():
        shutil.copytree(source, fork)
    fork.chmod(0o755)
    for directory in fork.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
    for target, replacement in replacements.items():
        dest = fork / Path(target).relative_to(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.chmod(0o644)
        shutil.copyfile(replacement, dest)
    modfile = build / "texture.mod"
    shutil.copyfile(FRONTEND / "go.mod", modfile)
    shutil.copyfile(FRONTEND / "go.sum", modfile.with_suffix(".sum"))
    subprocess.run(
        [
            "go",
            "mod",
            "edit",
            "-modfile",
            str(modfile),
            "-replace",
            "fyne.io/fyne/v2=" + str(fork),
        ],
        cwd=FRONTEND,
        env=env,
        check=True,
    )
    if args.prepare_only:
        print(modfile)
        return
    strategy = "stock-recreate" if args.stock else "reuse-rgba8-subimage-v1"
    tags = "release,no_animations"
    if os.uname().sysname == "Linux":
        tags += ",wayland"
    command = [
        "go",
        "build",
        "-mod=readonly",
        "-trimpath",
        "-tags",
        tags,
        "-ldflags",
        "-X main.textureUploadStrategy=" + strategy,
    ]
    if not args.stock:
        command += ["-modfile", str(modfile)]
    command += ["-o", str(build / "plotbench-fyne"), "."]
    subprocess.run(command, cwd=FRONTEND, env=env, check=True)
    (build / "texture-build.json").write_text(
        json.dumps(
            {
                "strategy": strategy,
                "fyne": module["Version"],
                "source_override_sha256": (
                    {
                        str(Path(p).relative_to(FRONTEND)): hashlib.sha256(
                            Path(p).read_bytes()
                        ).hexdigest()
                        for p in replacements.values()
                    }
                    if not args.stock
                    else {}
                ),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
