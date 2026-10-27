# Contributing

Thanks for your interest. SafetyLens is a small research codebase, so changes are reviewed
for correctness first and convenience second.

## Setup

```bash
uv sync --locked --python 3.11
make check        # lint, format, strict mypy, tests + coverage, audits, demo
```

Everything runs offline. No API keys are needed, and tests block network sockets.

## Rules for changes

- **Tests first for behaviour changes.** Statistical code needs a test against a known value or
  SciPy. Data-integrity code needs a test showing that invalid data can't reach a denominator.
- **Never weaken a test to make CI pass.** If a test is wrong, explain why in the PR.
- **Generated files are regenerated, not edited.** Historical outputs
  (`safetylens historical audit`), the demo example
  (`safetylens demo --write-example examples/synthetic-demo`) and
  `docs/DESIGN_COMPARISON.md` (`make design`) are checked for drift in CI.
- **Protocol changes go through `docs/DECISIONS.md`.** Never make one after seeing outcome
  data.
- **No raw model output, credentials or third-party benchmark text** in commits.
  `safetylens scan` and `safetylens release-audit` must pass, but they are safety nets: read
  [`docs/DATA_POLICY.md`](docs/DATA_POLICY.md).
- **No live API calls** in tests, CI or examples.

## Pull requests

Use the PR template. A PR is ready when CI is green, the template's review gates are ticked,
and the description says what was verified and what wasn't.
