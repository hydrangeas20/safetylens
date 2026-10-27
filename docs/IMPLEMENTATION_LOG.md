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
- No banner supplied; placeholder SVG used.
- Mixed-effects secondary model, tier B rubric, human-labelling tooling, automated
  best/worst-case bounds, live preflight and budget enforcement.
