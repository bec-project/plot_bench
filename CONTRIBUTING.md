# Contributing

Plotbench compares rendering implementations under a shared input and measurement
contract. Changes should improve usability or correctness without silently changing
what an existing benchmark measures.

Start with [setup](docs/setup.md) and [validation](docs/validation.md). Each frontend
is independently packaged; install only the components involved in your change,
using `./scripts/setup COMPONENT --dev`. Use Python 3.13 and retain lockfiles.
Include `rust` in setup when using the default source; Python source workflows
must select `--backend python` or `--backends python` explicitly.

Before submitting a change:

- Explain the concrete problem, resulting behavior, and relevant test evidence.
- Run the component's tests and formatting checks. Run protocol conformance checks
  for transport, source, scheduling, or measurement changes.
- Update user-facing instructions and examples when commands or behavior change.
- Include screenshots for UI changes, captured outside measurement windows.
- Keep generated results, build outputs, IDE settings, and local paths out of Git.

Python follows the root Ruff configuration and Black's 100-character line length.
Rust uses `cargo fmt` and Clippy; TypeScript uses its strict compiler and test suite.
Prefer simple functions and existing abstractions over a new plugin framework.

The web UI (matrix editor and source controls) is a Preact + Vite app in
[`core/webui`](core/webui). Its built output is committed — `plotbench matrix`
serves `core/src/plotbench/matrix_assets/` and both sources serve the single-file
`core/src/plotbench/controls.html` — so neither needs Node at runtime. After
changing the UI, run `npm run build` there and commit the regenerated output. See
its [README](core/webui/README.md).

See [adding a frontend](docs/frontends.md) before introducing a renderer. Its
limitations and custom rendering work must be explicit, and frontend code must
never replace the common data generator.

Contributions are made under the repository's [BSD 3-Clause license](LICENSE). Dependencies
keep their separate licensing terms; see [third-party notices](docs/licenses.md).
