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

- Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) for commit messages: `<type>[optional scope]: <description>`.
  For example, `fix(protocol): reject incomplete frames` or
  `docs: clarify setup instructions`.
- Explain the concrete problem, resulting behavior, and relevant test evidence.
- Run the component's tests and formatting checks. Run protocol conformance checks
  for transport, source, scheduling, or measurement changes.
- Update user-facing instructions and examples when commands or behavior change.
- Include screenshots for UI changes, captured outside measurement windows.
- Keep raw generated results, build outputs, IDE settings, and local paths out of Git.
  Community measurements are complete campaigns of the official baseline suite
  (`./scripts/plotbench run --baseline`), exported and submitted through the
  explicit [`website/results/` submission procedure](website/results/README.md);
  campaigns of other suites are not published.

Python follows the root Ruff configuration and Black's 100-character line length.
Rust uses `cargo fmt` and Clippy; TypeScript uses its strict compiler and test suite.
Prefer simple functions and existing abstractions over a new plugin framework.

The web UI (matrix editor and source controls) is a Preact + Vite app in
[`core/webui`](core/webui). Its built output is committed — `plotbench matrix`
serves `core/src/plotbench/matrix_assets/` and both sources serve the single-file
`core/src/plotbench/controls.html` — so neither needs Node at runtime. After
changing the UI, run `npm --prefix core/webui run typecheck` and
`npm --prefix core/webui run build` from the repository root and commit the
regenerated output. CI checks bundle reproducibility and browser interactions for
both pages. See its [README](core/webui/README.md).

The separate [community results website](website/README.md) uses React and Vite.
Run `npm --prefix website test` and `npm --prefix website run build` after changes,
and also after editing `scenarios/baseline.json`, because the site derives its
seven sections from that file. Its static output is generated in CI, not
committed. Result submissions must pass `npm --prefix website run validate`, which
accepts only complete benchmark-classified campaigns of the baseline suite; the
PR review covers data provenance and public-field review in addition to the
automated schema and baseline checks.

See [adding a frontend](docs/frontends.md) before introducing a renderer. Its
limitations and custom rendering work must be explicit, and frontend code must
never replace the common data generator.

Contributions are made under the repository's [BSD 3-Clause license](LICENSE).
Dependencies keep their separate licensing terms; see
[third-party licenses](THIRD-PARTY-LICENSES.md).
