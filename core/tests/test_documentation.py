"""Keep runnable documentation examples aligned with the CLI and suite schema."""

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from plotbench import cli
from plotbench.suites import plan_from_args, prepare_suite

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted(
    [
        *ROOT.glob("*.md"),
        *ROOT.glob("docs/*.md"),
        *ROOT.glob("core/README.md"),
        *ROOT.glob("core/webui/README.md"),
        *ROOT.glob("frontends/*/README.md"),
        *ROOT.glob("backends/*/README.md"),
    ]
)


def fenced_blocks(language):
    for path in DOCS:
        text = path.read_text()
        pattern = rf"^```(?:{language})\n(.*?)^```"
        for match in re.finditer(pattern, text, re.MULTILINE | re.DOTALL):
            line = text[: match.start()].count("\n") + 1
            yield f"{path.relative_to(ROOT)}:{line}", match.group(1)


def documented_commands(executable):
    snippets = list(fenced_blocks("sh|bash"))
    for path in DOCS:
        for match in re.finditer(r"(?<!`)`([^`\n]+)`(?!`)", path.read_text()):
            snippets.append((str(path.relative_to(ROOT)), match.group(1)))
    for location, snippet in snippets:
        for line in snippet.replace("\\\n", " ").splitlines():
            if executable + " " not in line:
                continue
            words = shlex.split(line, comments=True)
            if executable not in words:
                continue
            arguments = words[words.index(executable) + 1 :]
            if arguments:
                yield pytest.param(arguments, id=f"{location}: {' '.join(arguments)}")


@pytest.fixture
def cli_parser(monkeypatch):
    # Capture the real parser before dispatch, so examples never start a GUI,
    # install dependencies, run a campaign, or overwrite a report.
    class ParserReady(Exception):
        def __init__(self, parser):
            self.parser = parser

    def capture(parser, *args, **kwargs):
        raise ParserReady(parser)

    with monkeypatch.context() as patch:
        patch.setattr(argparse.ArgumentParser, "parse_args", capture)
        with pytest.raises(ParserReady) as ready:
            cli.main()
    return ready.value.parser


@pytest.mark.parametrize("arguments", list(documented_commands("./scripts/plotbench")))
def test_documented_cli_arguments_are_accepted(cli_parser, arguments):
    if "--help" in arguments or "-h" in arguments:
        with pytest.raises(SystemExit) as exited:
            cli_parser.parse_args(arguments)
        assert exited.value.code == 0
    else:
        args = cli_parser.parse_args(arguments)
        if args.command in ("run", "probe") and args.suite.parts[0] == "scenarios":
            args.suite = ROOT / args.suite
            assert plan_from_args(args, kind=args.command).jobs


@pytest.mark.parametrize("arguments", list(documented_commands("npm")))
def test_documented_npm_commands_have_a_package_and_script(arguments):
    package = ROOT / arguments[arguments.index("--prefix") + 1]
    manifest = json.loads((package / "package.json").read_text())
    assert (package / "package-lock.json").is_file()
    if "run" in arguments:
        script = arguments[arguments.index("run") + 1]
        assert script in manifest["scripts"]
    elif "test" in arguments:
        assert "test" in manifest["scripts"]
    else:
        assert "ci" in arguments


@pytest.mark.parametrize(
    "location,block", [pytest.param(*item, id=item[0]) for item in fenced_blocks("sh|bash")]
)
def test_documented_shell_blocks_parse(location, block):
    result = subprocess.run(["bash", "-n"], input=block, text=True, capture_output=True)
    assert result.returncode == 0, f"{location}: {result.stderr}"


@pytest.mark.parametrize(
    "location,block",
    [
        pytest.param(*item, id=item[0])
        for item in fenced_blocks("json")
        if item[0].startswith("docs/suites.md:")
    ],
)
def test_documented_suites_expand(location, block):
    plan = prepare_suite(json.loads(block))
    assert plan.jobs, location
