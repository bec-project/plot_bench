"""Build the Java adapter using the JDK and SHA-256-locked Maven Central JARs."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    jdk = os.environ.get("PLOTBENCH_JAVA_HOME")
    java = str(Path(jdk) / "bin/java") if jdk else shutil.which("java")
    javac = str(Path(jdk) / "bin/javac") if jdk else shutil.which("javac")
    jar = str(Path(jdk) / "bin/jar") if jdk else shutil.which("jar")
    if not all((java, javac, jar)):
        raise SystemExit(
            "JDK 17+ required; set PLOTBENCH_JAVA_HOME or add the JDK to PATH"
        )
    build = HERE / "build"
    cache = ROOT / ".cache/java"
    cache.mkdir(parents=True, exist_ok=True)
    libs = []
    test_jar = None
    for item in json.loads((HERE / "dependencies.lock.json").read_text()):
        if item["test"] and not args.test:
            continue
        dest = cache / item["file"]
        if not dest.exists():
            with urllib.request.urlopen(item["url"], timeout=60) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise SystemExit(f"Checksum mismatch: {item['file']}")
            dest.write_bytes(data)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != item["sha256"]:
            raise SystemExit(f"Cached dependency checksum mismatch: {dest}")
        if item["test"]:
            test_jar = dest
        else:
            libs.append(dest)
    # Remove stale generated classes/dependencies; never touch source or shared caches.
    if build.exists():
        shutil.rmtree(build)
    classes = build / "classes"
    classes.mkdir(parents=True)
    (build / "lib").mkdir()
    for lib in libs:
        shutil.copy2(lib, build / "lib" / lib.name)
    classpath = os.pathsep.join(map(str, libs))
    compiler = subprocess.check_output([javac, "-version"], text=True).strip()
    sources = sorted(map(str, (HERE / "src/main/java").rglob("*.java")))
    subprocess.run(
        [
            javac,
            "--release",
            "17",
            "-encoding",
            "UTF-8",
            "-cp",
            classpath,
            "-d",
            str(classes),
            *sources,
        ],
        check=True,
    )
    (classes / "build-info.json").write_text(
        json.dumps({"compiler": compiler, "release": 17})
    )
    manifest = build / "MANIFEST.MF"
    # java.util.jar requires continuation lines for long Class-Path values.
    entries = " ".join("lib/" + p.name for p in libs)
    value = "Class-Path: " + entries
    lines = [value[:70]]
    value = value[70:]
    while value:
        lines.append(" " + value[:69])
        value = value[69:]
    manifest.write_text(
        "Manifest-Version: 1.0\nMain-Class: org.plotbench.Main\n"
        + "\n".join(lines)
        + "\n\n"
    )
    subprocess.run(
        [
            jar,
            "--create",
            "--file",
            str(build / "plotbench-jfreechart.jar"),
            "--manifest",
            str(manifest),
            "-C",
            str(classes),
            ".",
        ],
        check=True,
    )
    if args.test:
        tests = build / "test-classes"
        tests.mkdir()
        test_cp = os.pathsep.join([str(classes), classpath, str(test_jar)])
        subprocess.run(
            [
                javac,
                "--release",
                "17",
                "-encoding",
                "UTF-8",
                "-cp",
                test_cp,
                "-d",
                str(tests),
                *map(str, sorted((HERE / "src/test/java").rglob("*.java"))),
            ],
            check=True,
        )
        subprocess.run(
            [
                java,
                "-Djava.awt.headless=true",
                "-jar",
                str(test_jar),
                "execute",
                "--class-path",
                os.pathsep.join([str(tests), str(classes), classpath]),
                "--scan-class-path",
                "--fail-if-no-tests",
                "--disable-banner",
            ],
            check=True,
        )
    print(
        "Built JFreeChart adapter (JDK 17 bytecode); dependencies verified against lock"
    )


if __name__ == "__main__":
    main()
