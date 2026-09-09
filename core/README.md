# Shared source and benchmark core

An independently packaged Python 3.13 component containing the deterministic
generator, streaming server, replay endpoint, shared client, sequential runner,
collector and offline reports. It has no Qt or plotting dependency.

The CLI defaults to the Rust source; build it with `./scripts/setup rust` for the
default workflow. For the core's Python source and tests without Rust, run from
the repository root:

```sh
./scripts/setup core --dev
./scripts/plotbench serve --backend python
.envs/plotting-benchmark/bin/python -m pytest core/tests
```

Install frontends separately before running a suite. Tests use ephemeral loopback
ports. Stop the interactive source with Ctrl+C before running the tests above.
See the [protocol and client API](../docs/protocol.md) and
[root README](../README.md).
