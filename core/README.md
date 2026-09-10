# Shared source and benchmark core

An independently packaged Python 3.13 component containing the deterministic
generator, streaming server, replay endpoint, shared client, sequential runner,
collector and offline reports. It has no Qt or plotting dependency.

The CLI defaults to the Rust source; build it with `./scripts/setup rust` for the
default workflow. For the core's Python source and tests without Rust, run from
the repository root:

```sh
./scripts/setup core --dev
.envs/plotting-benchmark/bin/python -m pytest core/tests
```

Start an interactive Python source and open [its controls](http://127.0.0.1:8765):

```sh
./scripts/plotbench serve --backend python
```

Install frontends separately before running a suite. Tests use ephemeral loopback
ports. Stop the interactive source with Ctrl+C when finished. The matrix editor
and source controls ship as prebuilt Preact assets; see the
[web UI development guide](webui/README.md).
See the [protocol and client API](../docs/protocol.md) and
[root README](../README.md).
