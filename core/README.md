# Shared source and benchmark core

An independently packaged Python 3.13 component containing the deterministic
generator, streaming server, replay endpoint, shared client, sequential runner,
collector and offline reports. It has no Qt or plotting dependency.

From the repository root:

```sh
./scripts/setup core
./scripts/plotbench serve
.envs/plotting-benchmark/bin/python -m pytest core/tests
```

Install frontends separately before running a suite. Tests use ephemeral loopback
ports. See the [protocol and client API](../docs/protocol.md) and
[root README](../README.md).
