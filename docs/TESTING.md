# Testing and verification

```bash
make check     # everything CI runs, offline
uv run pytest  # tests only (network sockets are blocked by pytest-socket)
```

Tests never make network calls or paid API calls. They don't read credentials; a fixture
removes `SAFETYLENS_ALLOW_LIVE`, `GROQ_API_KEY` and `ANTHROPIC_API_KEY` from the environment.

## What the tests establish

| Area | Test file | What it guarantees |
|---|---|---|
| Statistics | `unit/test_stats.py` | Wilson CI matches the archived values to 1e-12; exact McNemar matches SciPy `binomtest`; Holm ≥ raw and ≤ Bonferroni; Wilcoxon and paired t match SciPy; NaN input is rejected |
| Pairing | `unit/test_pairs.py` | Only complete valid pairs are kept; every exclusion is counted by reason; failed values never appear as False/0 |
| Response validity | `unit/test_quality.py` | The archived Qwen3-32B error string is rejected before judging; only `ok` is judgeable; finish reasons normalise correctly |
| Judge | `unit/test_judge.py` | Strict schema (no coercion, no extra or missing keys, consistent labels); failures have no labels; the judge prompt contains no cue, pretext or wording |
| Analysis | `unit/test_experiment_analysis.py` | Failed judgments and API errors are excluded from denominators; pretext is compared with filler; missing-data bounds are correct; Holm covers only primary contrasts |
| Items and config | `unit/test_items_config.py` | 16 / 6 conditions; core request constant; filler length-matched and neutral of the request; configs default to no live calls |
| Runner | `unit/test_runner.py` | Truncation retried at a larger budget; error text never becomes `ok`; resume appends nothing; live providers blocked |
| Providers | `unit/test_providers.py` | Live guard needs config and env; adapters map finish reasons and exceptions (stub clients); replay is strict |
| Power simulation | `unit/test_design.py` | Exact McNemar rejection table matches SciPy cell by cell; type I error controlled under correlated nulls; a preamble-only model has zero true pretext effect |
| Item review | `unit/test_review.py` | Two distinct reviewers required; failures block; the CLI gate exits non-zero |
| Scanning | `unit/test_scan.py`, `unit/test_release_audit.py` | Secrets, raw-text columns, unredacted responses, emails and local paths are found, **including in deleted files and unmerged branches**; archive overlap is detected |
| Docs | `unit/test_docs.py` | Local links and images resolve; README diagram equals its source; fragile Mermaid syntax guarded |
| Historical audit | `integration/test_historical.py` | Manifest pins the archive commit; redacted files contain no raw text; flag counts (Qwen 42/42 errors, 6 and 3 judge failures); the original statistics are reproduced to 1e-9; committed outputs match regeneration |
| End to end | `integration/test_e2e.py` | Synthetic run recovers the known ground truth (including the filler control); strict replay is identical; the committed example matches regeneration; CLI commands work offline |

## CI jobs (`.github/workflows/ci.yml`)

| Job | Runs |
|---|---|
| Lint, format, type check | `ruff check`, `ruff format --check`, `mypy --strict` |
| Tests and coverage | `pytest --cov` (fails under 85%) |
| Historical audit regression | `historical verify`, then `historical audit` with a no-diff check |
| Offline end-to-end replay | `safetylens demo`, then a check that live execution is refused |
| Secret, redaction and history audit | `safetylens scan`, `safetylens release-audit` over full history, and a check that workflows use no secrets |
| README and diagram validation | Mermaid CLI parses every README diagram; assets exist |

## What is not tested

- **Live provider adapters against real APIs.** Only stub clients are used.
- **Judge validity.** No human labels exist yet.
- **Visual rendering on github.com.** The README is checked through the GitHub API, the Mermaid
  CLI and a headless-browser preview of GitHub's HTML, but not by viewing the live page.
