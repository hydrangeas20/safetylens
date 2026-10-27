# SafetyLens v1 experimental protocol (DRAFT)

> **Status: draft. Not frozen, not pre-registered, not approved.** Open choices are listed in
> [`DECISIONS.md`](DECISIONS.md). No data under this protocol has been collected. Freezing
> happens by tagging a reviewed version of this file *before* any paid call.

## 1. Research question

How do three features of a prompt each change an LLM's **harmful compliance** when the
underlying harmful request is held constant?

- **(A) Evaluation cue:** an explicit statement that the prompt is part of a safety evaluation.
- **(B) Wording register:** terse benchmark phrasing vs natural conversational phrasing, with
  no justification added.
- **(C) Pretext:** a persona or justification (fiction, professional role).

The archived experiment mixed B and C, and its labels treated all refusal as safe
([`DEFECTS.md`](DEFECTS.md) W1–W3). This design separates them.

## 2. Items

Items are defined in JSONL and validated by `safetylens.items.Item`.

| Tier | Meaning | `compliance_appropriate` | Role |
|---|---|---|---|
| A | Harmful in any stated context | `never` | Primary analysis |
| B | Dual-use; a stated context can legitimately justify help | `context_dependent` | Secondary (appropriateness), separate rubric |
| C | Benign, including requests that look harmful but aren't | `always` | Over-refusal |

- **Fields per item:** `core_request` (fixed text), `terse` and `conversational` (each must
  contain `core_request` verbatim), and `pretexts.fiction` / `pretexts.professional` (framing
  sentences only, never restating or extending the request).
- **Overrides:** optional hand-written versions per condition. They must also contain
  `core_request` verbatim.
- **Sourcing:** prefer established benchmarks (e.g. HarmBench, StrongREJECT for tier A; XSTest
  for tier C) after a licence review. Record `source` for every item.
- **Equivalence review:** a second reviewer confirms each variant keeps the request unchanged,
  recorded in `data/items/equivalence_review.csv` (to be created).
- **Target sizes:** about 120 tier A, 40 tier B and 60 tier C items. Final tier A size comes
  from the power analysis (§7) and the design decision (DEC-1).

## 3. Conditions

`safetylens.items` renders each condition as `[cue] + [pretext] + [terse | conversational
request]`. The cue text is fixed and versioned (`CUE_VERSION = cue-v1-draft`).

- **Full design:** 2 × 2 × 3 = 12 conditions per item.
- **Compact design:** 5 conditions, varying one factor at a time from the benchmark baseline
  (`cue=none|reg=terse|pre=none`).

The trade-offs are in [`DESIGN_COMPARISON.md`](DESIGN_COMPARISON.md).

## 4. Outcomes

| Role | Outcome | Population |
|---|---|---|
| Primary | `harmful_compliance` (judge, binary) | Tier A |
| Secondary | `refused`; `partial_compliance`; 1–10 `safety_score` (descriptive only) | Tier A |
| Secondary | Over-refusal rate at baseline | Tier C |
| Secondary | Appropriateness, using a separate rubric still to be written | Tier B |
| Data quality | Response status, truncation rate, judge failure rate, exclusions per model and contrast | All |

## 5. Primary contrasts and tests

Per model, four contrasts, each treatment minus reference:

1. cue explicit vs none
2. conversational vs terse
3. fiction pretext vs none
4. professional pretext vs none

- **Compact design:** one matched pair per item; exact two-sided McNemar.
- **Full design:** each item's score is the mean of its matched-pair differences (6 pairs for
  cue and register, 4 for each pretext level), tested with a two-sided Wilcoxon signed-rank
  test on item scores.
- **Both designs:** effect = mean item score, with a percentile bootstrap 95% CI over items
  (10,000 resamples, fixed seed).
- **Multiple comparisons:** Holm across all primary tests (4 contrasts × number of models),
  family-wise α = 0.05.
- **Pre-specified secondary analyses:**
  - the same contrasts on `refused`
  - a mixed-effects logistic regression with all factors, their interactions and random item
    intercepts (not yet implemented; see DEC-6)
  - the stability subsample (§8)

## 6. Validity and missing-data rules (implemented)

- A response is analysable only if its status is `ok`: a complete finish reason, no API error,
  not error text, not empty, not filtered.
- Truncated responses are retried at `truncation_retry_max_tokens`. If still truncated, they
  stay `truncated` and are never judged.
- A judgment counts only if the output parses strictly as `JudgeVerdict` and is internally
  consistent. Failed judgments carry no labels and are excluded from every denominator, with
  the count reported by reason.
- An item enters a contrast only if all of its matched pairs are valid (complete-case). The
  alternative is DEC-4.
- No imputation. If exclusions go above 5% in any model × contrast, best-case/worst-case bounds
  become a required secondary analysis (not yet automated; see DEC-4).

## 7. Sample size

[`DESIGN_COMPARISON.md`](DESIGN_COMPARISON.md) gives simulated power under stated assumptions
for both designs, at the worst-case Holm threshold. The assumptions (baseline rate, effect
sizes, item heterogeneity) are guesses. The pilot (§10) should estimate them before the
protocol is frozen.

## 8. Sampling

- **Primary:** one sample per cell at temperature 0. `seed` is set and the provider's model
  fingerprint is recorded.
- **Stability subsample:** a pre-specified 20% of items, 5 samples at T = 0.7, to report how
  often answers change between samples (DEC-5).

## 9. Judge and validation

- **Blinding:** the judge receives the item's `core_request` and the response only. It never
  sees the cue, pretext, wording or model name.
- **Rubric:** `v1-draft` is in `safetylens/judge.py`. Rubric versions are hashed into every
  judgment.
- **Human validation (not done):**
  - two human raters label a stratified held-out set of about 200 responses
  - the rubric may be revised on a separate development set only
  - acceptance requires judge–human Cohen's κ ≥ 0.70 on `harmful_compliance` and reported
    inter-rater κ
  - a second judge from a different model family labels a 20% subsample
- **No claims of judge validity** are made until this protocol is carried out and reported.

## 10. Gates before any paid call

1. Protocol and decisions approved; protocol tagged as frozen.
2. Items written, licence-reviewed and equivalence-reviewed.
3. Judge validated per §9.
4. Live execution implemented with a preflight call per model (confirming parameters are
   accepted and finish reasons are returned) and hard budget enforcement. **Neither exists
   yet; `safetylens run` refuses live providers.**
5. Pilot of about 10% of items on one model, with an approved budget.
6. Full run, with an approved budget.
