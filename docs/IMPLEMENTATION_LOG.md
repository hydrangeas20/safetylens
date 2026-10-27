# Implementation log

Chronological record of engineering work. Times are America/Toronto.

## 2026-10-26 / 27: engineering sprint 1

**Scope (approved):** repository bootstrap and historical audit; modular evaluation framework
with offline replay and integrity safeguards; CI, docs and README. No paid calls, no merge, no
visibility change, no change to `safetylens-research`.

### Bootstrap
- `main` bootstrapped with `.gitignore` and a placeholder README (commit `e28f8a0`). All other
  work is on `feat/foundation`.
- Python 3.11.17, uv-managed, `uv.lock` committed. Runtime dependencies: numpy, pandas, scipy,
  pydantic, pyyaml. Live SDKs are an optional `[live]` extra that CI doesn't install.

### Historical integrity
- Archive confirmed at `b5d0dba` (2 commits). Its files are byte-identical to the zip reviewed
  earlier.
- `historical/MANIFEST.json`: SHA-256 for all 16 archive files plus the 6 derived files.
  Verified against the local archive checkout (`SAFETYLENS_ARCHIVE` test passes locally; skipped
  in CI because the archive is private).
- Redacted data replaces prompt and response text with SHA-256 hashes and derived features.
  Judge reasons were reviewed and kept; they contain meta-descriptions only.
- Reproduction of the original statistics matches all three archived tables to 1e-9.
- Flags: Qwen3-32B 42/42 API errors; Llama-3.1-8B 6 judge failures; Llama-3.3-70B 3; placeholder
  prompt on 2 rows per model; truncation heuristic 19 and 24 rows.
- Truncation heuristic chosen from the archived length distribution: every response without
  terminal punctuation is ≥ 1170 characters, so the threshold is 1000 characters.
- Corrected exploratory analysis written. The truncation sensitivity result (most pairs
  removed; refusal effect gone) is interpreted in the report as evidence of dependence on
  possibly-truncated responses, not as a robustness check.

### Framework
- Modules: `records`, `quality`, `config`, `items`, `providers/{base,fake,replay,live}`,
  `storage`, `runner`, `judge`, `analysis/{stats,pairs,experiment}`, `design`, `synthetic`,
  `scan`, `cli`.
- Live calls need both `allow_live: true` and `SAFETYLENS_ALLOW_LIVE=1`. On top of that,
  `safetylens run` refuses live providers outright until preflight and budget enforcement exist.
- Synthetic run: fake profiles with a known injected pretext effect plus persistent API errors,
  transient error-text responses, truncation, missing finish reasons and malformed judge
  output. Strict replay reproduces results exactly.

### Issues found and fixed during the sprint
- Fake-provider failures were all transient, so retries hid them and exclusion paths went
  untested. Added persistent failure modes.
- Report row order depended on dict insertion order: reports rendered from memory and from
  sorted-key JSON differed. The renderer now iterates in sorted order.
- An end-to-end test wrongly expected replay of the compact design to miss the full-design
  cassette. Compact conditions are a subset with identical prompts, so a hit is correct. Test
  replaced with an item-change miss test.
- The design comparison compared designs at equal item counts only. Added an equal-cost column
  and the within-item independence caveat. Null calibration checked with 20,000 replications at
  α = 0.05/12: McNemar is conservative, Wilcoxon on item scores holds its nominal level.
- Renamed decision IDs to `DEC-n` to avoid clashing with defect IDs `D1–D10`.

### Not done (see handoff and `DECISIONS.md`)
- No banner supplied; placeholder SVG used. (Resolved 2026-10-27: approved banner committed.)
- Mixed-effects secondary model, tier B rubric, human-labelling tooling, automated
  best/worst-case bounds, live preflight and budget enforcement.

### Verification
- Local `make check` (lint, format, mypy, tests, manifest verify, scan, synthetic e2e, audit
  regeneration with no drift): exit 0. 204 passed, 1 skipped (archive-hash test; passes
  locally with `SAFETYLENS_ARCHIVE` set), coverage 97.1%.
- PR #1 opened against `main`. GitHub Actions run 40446500656 on `8553ee5`: all five jobs
  succeeded (lint/type, tests and coverage, historical regression, offline e2e, safety scan).
  Job logs could not be downloaded from this workspace (blob storage not on the network
  allowlist), so test counts above are from the identical local command.
- `safetylens-research` remains at `b5d0dba` (checked with `git ls-remote`).

## 2026-10-27: README repair and visual presentation (PR #1 hardening)

### Root cause of "Unable to display rich text"
- GitHub's server-side Markdown rendering was fine (tables, alert, images and badge all
  present in the API-rendered HTML). The failure was the client-side Mermaid render.
- The architecture node `H[(Archive<br/>safetylens-research@b5d0dba)]` contains `@`. Mermaid 11
  tokenises `name@` as an edge ID (`LINK_ID`, the `e1@-->` syntax), so the whole diagram fails
  to parse. Mermaid CLI 11.16.0: `Parse error on line 17 ... got 'LINK_ID'`.
- Minimal reproduction: `A[x@y] --> B` fails. The full original diagram renders once only the
  `@` is removed; `<br/>`, `&` edges, `×` and subgraphs were not the cause.

### Changes
- Diagram rewritten with quoted labels and no `@`, `<br/>` or `&` edges. Source of truth is
  `docs/diagrams/architecture.mmd`, embedded verbatim in the README. Static fallback rendered to
  `docs/diagrams/architecture.png` with the Mermaid CLI. (An SVG export was rejected because its
  labels use `foreignObject`, which some viewers drop when the SVG is embedded as an image.)
- Approved banner committed unmodified as `assets/safetylens-hero.png` (SHA-256 identical to the
  supplied file). Placeholder SVG removed.
- README restructured: banner, positioning sentence, badges, research question, factors,
  methodology, architecture, implementation/verification status, historical audit (separate
  from validated results), reproducibility, data safety, limitations and next steps.
- New `tests/unit/test_docs.py`: local links and images resolve in all docs, README diagram
  equals the source file, fragile Mermaid syntax guarded, labels quoted, banner present.
- New CI job `docs` parses every README Mermaid block with `@mermaid-js/mermaid-cli@11.16.0`.
  Checked locally: the old README block exits 1 and the new one exits 0.

### Verification (no browser available)
- Local `make check`: exit 0; 220 passed, 1 skipped; coverage 97.1%.
- GitHub Actions run 40526815192 on `002f498`: all six jobs succeeded, including the new
  `README and diagram validation` job (Mermaid CLI parse of the README block on a GitHub runner).
- GitHub REST API (`/readme`, HTML media type) on `feat/foundation`: 10 sections, 5 tables, 3 code
  blocks, the important-alert, one Mermaid section, banner `<img src="assets/safetylens-hero.png">`,
  CI badge and two shields.io badges proxied through camo. The banner's git blob SHA on GitHub
  equals the local file's.
- Offline preview: GitHub's API-rendered HTML loaded in headless Chromium, with the embedded
  Mermaid source rendered client-side by mermaid.js 11 (the step GitHub performs in its viewer
  iframe). Mermaid rendered without error. Banner loaded at 900x309 (desktop) and 358x123
  (390 px phone); no horizontal scroll. External badges could not load in the sandbox (no
  network access to shields.io/camo); this is expected and not a repository issue.
- **Unverified:** visual inspection of the live GitHub page itself (no signed-in browser for
  the private repository). GitHub's Mermaid viewer version is not published; compatibility is
  inferred from Mermaid 11.16 parsing plus conservative syntax.
- CI run 40529077472 on `dcc9e4e` failed in `Tests and coverage`: the new link checker treated
  an `<img src=...>` quoted inside inline code in this log as a real image. The log-only commit
  had been pushed without rerunning the suite locally. Fix: the checker now ignores inline code
  and fenced blocks, and a new test confirms it still catches real broken links and images.

## 2026-10-27: public-release readiness (branch `release/public-readiness`)

### Disclosure audit
- Mirrored the repository with all branches and `refs/pull/*`, then scanned all 94 historical
  blobs and 8 commit messages. Checked archive object overlap against a local archive checkout,
  searched for all 42 archive prompts and 415 response windows, and read every retained judge
  rationale. No blocking content. Verdict and manual items: `docs/PUBLIC_RELEASE_AUDIT.md`.
- Added `safetylens release-audit` (full-history scan, email and local-path checks, archive
  overlap with an allowlist) and run it in CI with `fetch-depth: 0`. Writing its tests caught
  two bugs in the tool itself: the scanner allowlist was matched against `path@sha` labels, and
  identical directory trees were flagged as archive leaks. Trees are now excluded; commits and
  blobs are checked.

### Protocol rigour
- New pretext level `filler`: a length-matched neutral sentence, validated within
  max(2 words, 25%) of the mean pretext length. Full design is now 16 conditions, compact 6.
- Primary pretext contrasts are now pretext vs filler. `filler_vs_none` and
  `cue_explicit_vs_filler` are reported as controls outside the Holm family.
- Every contrast reports exclusion rate, a >5% flag and worst/best-case missing-data bounds.
- Power model rewritten: separate preamble and content effects, item random slopes, reported
  probability-scale estimands, and a type I table under correlated nulls (0.030–0.050 at
  nominal 0.05).
- Protocol rewritten with estimands, hypotheses, controls, paraphrase plan, missing-data and
  truncation policies. Added a two-reviewer item-equivalence gate (`safetylens.review`, CLI
  `--review --require-approved`), checklist and template.

### Demonstration and presentation
- `safetylens demo`: one-command synthetic run plus strict replay, with a third fake model
  (`fake-prefix`) showing why the filler control matters. Committed example at
  `examples/synthetic-demo/` and checked for drift in tests.
- README rewritten for a first-screen summary. An MIT licence was added after a dependency
  licence review, then removed at the owner's request (no project licence).
  Added SECURITY.md, CONTRIBUTING.md, ARCHITECTURE.md and TESTING.md. Removed links to the
  private archive.
- CI run on `52e231a` failed in the history-audit job: the new audit flagged its own regex
  source and the fabricated email and home-directory inputs in its tests. The local run had
  passed only because it was executed before committing, so the new files weren't in history
  yet. Fixes: the tool's definition file is allowlisted by path for all checks, like
  `scan.py`; tests build fake values at runtime; the one pushed test blob is pinned as a
  reviewed false positive by exact blob SHA. Release audits are now run after committing, and
  documentation describes detected patterns without quoting them.

## 2026-10-27: focused sprint after PR #1 merged (branch `release/v1-public-audit`)

- PR #1 was squash-merged, so `main` (`f32f80d`) no longer shares commits with PR #2. Its tree
  is byte-identical to PR #1's head, so PR #2's three commits were cherry-picked onto `main`
  unchanged; the resulting tree equals PR #2's head.
- **Audit:** fresh mirror with all `refs/pull/*`; `release-audit --archive` gives 0 blocking
  findings over 12 commits and 140 blobs. Actions: 9 runs, 0 artifacts, no secrets or caches.
  Logs can't be downloaded here, so every CI job's commands were rerun locally and the full
  output was scanned. `docs/PUBLIC_RELEASE_AUDIT.md` rewritten as a concise current report:
  PASS.
- **Protocol:** evaluation-framing effects vs evaluation awareness (§1.1, with a planned
  manipulation check), experimental units, randomization, pre-specified exclusions, and a full
  human judge-validation plan. The κ precision claim was checked numerically and corrected:
  200 responses give about ±0.09, not ±0.07. New open decisions DEC-14 to DEC-16.
- **Randomization implemented:** `runner.collect` now shuffles the full cell plan with a seeded
  RNG (`sampling.randomize_order`, default on). Tests check that it is reproducible, complete,
  seed-dependent, and off when disabled. The committed demo example is unchanged, because fake
  outputs depend on the cell, not the call order.
