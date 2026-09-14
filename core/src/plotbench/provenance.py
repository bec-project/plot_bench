"""Record source, lockfile and actual executable identities outside measured work."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = {
    "fyne": "frontends/fyne/build/plotbench-fyne",
    "rust": "backends/rust/target/release/plotbench-source-rust",
    "iced": "frontends/iced/target/release/plotbench-iced",
    "plotly": "frontends/plotly/dist",
    "qtgraphs-cpp": "frontends/qtgraphs-cpp/build/plotbench-qtgraphs-cpp",
}
_EXCLUDED_DIRECTORIES = {
    ".git",
    ".idea",
    ".envs",
    ".cache",
    ".cargo-cache",
    ".qa-results",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "target",
    "dist",
    "build",
    "results",
    "test-results",
    "playwright-report",
    "screenshots",
    "audit",
    "docs",
}
_SOURCE_SUFFIXES = {
    ".go",
    ".mod",
    ".sum",
    ".py",
    ".rs",
    ".toml",
    ".lock",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".html",
    ".css",
    ".wgsl",
    ".glsl",
    ".vert",
    ".frag",
    ".sh",
    ".cpp",
    ".h",
    ".qml",
    ".cmake",
}


def source_hash(directory, *, checkout=False):
    """Fingerprint code/configuration and bundled assets, including untracked files."""
    directory = Path(directory)
    files = []
    # Prune dependencies and outputs before traversal, including ignored QA artifacts.
    for current, directories, names in os.walk(directory):
        directories[:] = sorted(name for name in directories if name not in _EXCLUDED_DIRECTORIES)
        if checkout and Path(current) == directory:
            # User-selected report directories outside the source packages must
            # not invalidate a run simply because it writes its own results.
            directories[:] = [
                name
                for name in directories
                if name in {"core", "frontends", "backends", "scripts", "scenarios"}
            ]
            names = [
                name
                for name in names
                if name
                in {
                    ".python-version",
                    ".uv-version",
                    ".npmrc",
                    ".nvmrc",
                    ".node-version",
                    "rust-toolchain",
                    "rust-toolchain.toml",
                    "pyproject.toml",
                    "uv.lock",
                    "Cargo.toml",
                    "Cargo.lock",
                    "package.json",
                    "package-lock.json",
                    "ruff.toml",
                }
            ]
        for name in sorted(names):
            path = Path(current) / name
            relative = path.relative_to(directory)
            if name == ".DS_Store":
                continue
            if (
                path.suffix in _SOURCE_SUFFIXES
                or name
                in {
                    ".npmrc",
                    ".nvmrc",
                    ".node-version",
                    "rust-toolchain",
                    ".python-version",
                    ".uv-version",
                    "CMakeLists.txt",
                }
                or {"src", "assets", "public", "scripts"}.intersection(relative.parts[:-1])
            ):
                files.append(path)
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(directory).as_posix().encode() + b"\0")
        digest.update(file_hash(path).encode() + b"\0")
    return digest.hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git_output(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL, timeout=10
    )


def capture_provenance(root=ROOT):
    root = Path(root)
    result = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "git": None,
        "source_sha256": source_hash(root, checkout=True),
    }
    try:
        top = Path(git_output(root, "rev-parse", "--show-toplevel").decode().strip())
        if top.resolve() == root.resolve():
            result["git"] = {
                "commit": git_output(root, "rev-parse", "HEAD").decode().strip(),
                "dirty": bool(git_output(root, "status", "--porcelain")),
                "tracked_diff_sha256": hashlib.sha256(
                    git_output(root, "diff", "HEAD", "--binary")
                ).hexdigest(),
            }
    except (OSError, subprocess.SubprocessError) as exc:
        result["git_error"] = type(exc).__name__
    result["lockfiles"] = {
        str(path.relative_to(root)): file_hash(path)
        for pattern in (
            "core/uv.lock",
            "frontends/*/uv.lock",
            "frontends/*/Cargo.lock",
            "frontends/*/go.mod",
            "frontends/*/go.sum",
            "backends/*/Cargo.lock",
            "frontends/*/package-lock.json",
        )
        for path in sorted(root.glob(pattern))
    }
    return result


def component_source_hash(component, root=ROOT):
    """Hash component sources, excluding dependencies and generated build outputs."""
    relative = "backends/rust" if component == "rust" else f"frontends/{component}"
    directory = Path(root) / relative
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    return source_hash(directory)


def _manifest_path(component, path):
    return (path if component == "plotly" else path.parent) / "plotbench-build.json"


def artifact_identity(component, root=ROOT):
    root = Path(root)
    path = root / ARTIFACTS[component]
    manifest = _manifest_path(component, path)
    entrypoint = path / "index.html" if component == "plotly" else path
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    files = [p for p in files if p != manifest]
    identity = {
        "path": ARTIFACTS[component],
        "entrypoint_present": entrypoint.is_file(),
        "files": {p.relative_to(root).as_posix(): file_hash(p) for p in files if p.is_file()},
        "build": None,
        "matches_sources": None,
        "matches_artifact": None,
    }
    if manifest.exists():
        try:
            build = json.loads(manifest.read_text())
            if (
                not isinstance(build, dict)
                or not isinstance(build.get("source_sha256"), str)
                or not isinstance(build.get("files"), dict)
                or not all(
                    isinstance(k, str) and isinstance(v, str) for k, v in build["files"].items()
                )
            ):
                raise ValueError(
                    "Build manifest must contain a source hash and artifact file hashes"
                )
        except (OSError, ValueError) as exc:
            identity.update(build_error=str(exc), matches_sources=False, matches_artifact=False)
            return identity
        identity["build"] = build
        identity["matches_sources"] = build["source_sha256"] == component_source_hash(
            component, root
        )
        identity["matches_artifact"] = (
            identity["entrypoint_present"] and build["files"] == identity["files"]
        )
    return identity


def require_current_artifact(component, root=ROOT):
    identity = artifact_identity(component, root)
    if not identity.get("matches_sources") or not identity.get("matches_artifact"):
        raise RuntimeError(
            f"{component} build is missing, changed, or unverified; run ./scripts/setup {component} before measuring"
        )
    return identity


def record_build(component, root=ROOT):
    path = Path(root) / ARTIFACTS[component]
    entrypoint = path / "index.html" if component == "plotly" else path
    if not entrypoint.is_file():
        raise FileNotFoundError(entrypoint)
    identity = artifact_identity(component, root)
    provenance = capture_provenance(root)
    record = dict(
        provenance,
        component=component,
        checkout_source_sha256=provenance["source_sha256"],
        source_sha256=component_source_hash(component, root),
        files=identity["files"],
    )
    manifest = _manifest_path(component, path)
    manifest.write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ARTIFACTS:
        raise SystemExit(
            "Usage: python -m plotbench.provenance rust|iced|fyne|plotly|qtgraphs-cpp (after building)"
        )
    record_build(sys.argv[1])
