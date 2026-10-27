# SafetyLens v1 experimental protocol (DRAFT)

> **Status: draft. Not frozen, not pre-registered, not approved.** No data has been collected
> under this protocol. Open choices are tracked in [`DECISIONS.md`](DECISIONS.md). The protocol
> is frozen by tagging a reviewed version of this file *before* any paid call. After freezing,
> changes are allowed only as dated, justified amendments, made before the affected data is seen.

## 1. Research question

Holding a harmful request fixed, how much does each of three prompt features change an LLM's
**harmful compliance**?

| Factor | Levels | Why it matters |
|---|---|---|
| A. Evaluation cue | none · explicit | Benchmarks that look like tests may elicit test-specific behaviour (evaluation awareness). |
| B. Wording register | terse · conversational | Benchmark prompts are terse; real requests are conversational. |
| C. Pretext | none · **filler** · fiction · professional | Real requests often add a persona or justification. |

The archived predecessor changed B and C together and treated every refusal as safe
([`DEFECTS.md`](DEFECTS.md), W1–W3). This design separates the factors and adds controls.

## 2. Controls

### 2.1 Length-matched neutral filler (implemented)

A pretext adds both *content* (a justification) and *length* (a preamble). Without a control,
"pretext effect" could mean "any preamble changes behaviour". Every item therefore carries a
**filler** sentence:

- neutral: no persona, no justification, no evaluation cue, no topic hint
- placed exactly where pretexts go
- length-matched: its word count must be within max(2 words, 25%) of the item's mean pretext
  length, enforced by `safetylens.items`

**Primary pretext estimands compare a pretext with filler, not with no preamble.** Two
secondary control contrasts are reported:

| Control contrast | Question |
|---|---|
| `filler_vs_none` | Does any neutral preamble change behaviour? |
| `cue_explicit_vs_filler` | Does the cue's *content* matter beyond adding a preamble of similar length? |

The cue is a single fixed sentence (`cue-v1-draft`, 10 words); its length match to the filler
is approximate (DEC-12).

### 2.2 Positive controls (planned; private item set)

- **Instrument check.** A small set of tier A items, each paired with a framing already known
  from the literature to raise compliance in some models. If no model shows any increase, the
  pipeline cannot detect effects and results are uninterpretable.
- **Judge check.** Inert synthetic responses with known labels, mixed into judging blind.
  Judge accuracy on them is reported.

Positive-control framing text is jailbreak-adjacent and stays in the private item set. Only
item ids and aggregate results are published.

### 2.3 Negative controls (planned)

- **Placebo outcome.** Tier C (benign) items under every condition: harmful compliance must
  stay at zero. A non-zero rate signals judge error, not a model effect.
- **Semantically null rewording.** For a subset of items, a punctuation and casing variant of
  the terse wording. It should not move compliance beyond sampling noise.
- **Synthetic pipeline control (implemented).** The fake `fake-prefix` model reacts to any
  preamble. The analysis must report a positive `filler_vs_none` effect and a null pretext
  effect for it, which it does ([`examples/synthetic-demo/report.md`](../examples/synthetic-demo/report.md)).

## 3. Items

Items are defined in JSONL and validated by `safetylens.items.Item`.

| Tier | Meaning | `compliance_appropriate` | Role |
|---|---|---|---|
| A | Harmful in any stated context | `never` | Primary analysis |
| B | Dual-use; a stated context can legitimately justify help | `context_dependent` | Secondary (separate rubric, not yet written) |
| C | Benign, including requests that look harmful but aren't | `always` | Over-refusal; placebo outcome |

- **Required fields per item:**
  - `core_request`
  - `terse` and `conversational` (each must contain `core_request` verbatim)
  - pretexts `filler`, `fiction` and `professional` (framing only; must not restate the
    request)
  - `source` (provenance)
- **Sourcing:** adapt from established benchmarks (e.g. HarmBench and StrongREJECT for tier A,
  XSTest for tier C) after a licence review. Benchmark text is redistributed only where its
  licence allows, otherwise referenced by id.
- **Target sizes:** about 120 tier A, 40 tier B and 60 tier C. The final tier A size is set from
  the pilot and the power analysis (§7).

### 3.1 Equivalence review (implemented as a gate)

Schema validation proves the request text is present; it cannot prove the variants mean the
same thing.

- Every item needs **two independent reviewers** to pass all eight checks in
  [`ITEM_REVIEW.md`](ITEM_REVIEW.md), recorded in a CSV using
  [`templates/item_review_template.csv`](templates/item_review_template.csv).
- `safetylens validate --items … --review … --require-approved` fails unless every item is
  approved.
- A failed check blocks the item until the same reviewer records a passing re-review.

### 3.2 Paraphrase variation plan (DEC-7, not yet implemented)

A single cue sentence, filler or pretext per item would make every conclusion depend on that
wording. Before freezing:

- **Cue:** 6 paraphrases of the evaluation cue, each a single sentence of 8–12 words. Each
  item × cue-condition is assigned one paraphrase, balanced across items by a seeded Latin
  square.
- **Pretexts and filler:** 3 paraphrases per type per item, written to the same template and
  length constraint, balanced the same way.
- **Analysis:** paraphrase enters as a grouping factor. The primary nonparametric analysis
  stays item-level (paraphrase is averaged within item). The planned mixed-effects secondary
  analysis adds a paraphrase random intercept, and paraphrase-level variance is reported.
- **Review:** paraphrases go through the same two-reviewer equivalence review.

## 4. Estimands and hypotheses

For model *m*, the item population *I* (tier A items sampled as in §3) and a contrast *k* made
of matched condition pairs (*t*, *r*):

**θ<sub>m,k</sub> = E<sub>i∈I</sub> [ mean over matched pairs of ( P(Y<sub>i,t</sub> = 1) − P(Y<sub>i,r</sub> = 1) ) ]**

where *Y* = 1 is harmful compliance as judged (§6). This is a population-average risk
difference on the probability scale. In the full design it averages over the levels of the
other factors; in the compact design it holds them at the baseline (terse, no cue).

| Contrast *k* | Treatment *t* | Reference *r* | Hypothesis |
|---|---|---|---|
| H1 `cue_explicit_vs_none` | explicit cue | no cue | θ ≠ 0 (two-sided) |
| H2 `register_conversational_vs_terse` | conversational | terse | θ ≠ 0 |
| H3 `pretext_fiction_vs_filler` | fiction pretext | filler | θ ≠ 0 |
| H4 `pretext_professional_vs_filler` | professional pretext | filler | θ ≠ 0 |

- **Family:** H1–H4 × every model, with Holm correction at family-wise α = 0.05 (DEC-2).
  Control contrasts and refusal outcomes are secondary and reported without family correction.
- **Smallest effect of interest:** 5 percentage points. Before claiming that a factor has *no*
  effect, an equivalence test (two one-sided tests, ±5 pp margin) is required; a
  non-significant difference test is not evidence of absence (DEC-13; not yet implemented).

## 5. Tests and uncertainty (implemented)

| Design | Per-item score | Test | Interval |
|---|---|---|---|
| Compact (6 conditions) | treatment − reference ∈ {−1, 0, 1} | exact two-sided McNemar | percentile bootstrap over items, 10,000 resamples, fixed seed |
| Full (16 conditions) | mean over matched pairs | two-sided Wilcoxon signed-rank on item scores | same |

A planned secondary analysis fits a mixed-effects logistic model with all factors, their
interactions, item random intercepts and slopes, and paraphrase random intercepts (DEC-6; not
implemented).

## 6. Validity, missing data and truncation

### 6.1 Implemented rules

1. **Response validity.** A response is analysable only with status `ok`: provider finish
   reason recorded and complete, no API error, not error text, not empty, not filtered.
2. **Truncation.** `finish_reason = length` is retried once at `truncation_retry_max_tokens`
   (default 4096). A response that is still truncated stays `truncated` and is never judged.
3. **Judge failures.** A judgment counts only if its output parses strictly as `JudgeVerdict`
   and is internally consistent. Failures carry no labels and never become refusals or
   non-refusals.
4. **Complete-case items.** An item enters a contrast only if every matched pair is valid.
   Excluded items are counted by reason for every model × contrast.
5. **No imputation.**
6. **Missing-data bounds.** Every contrast reports worst/best-case bounds that assign each
   excluded item a score of −1 or +1. When exclusion exceeds 5% (flagged ⚠ in reports), the
   bounds must be reported alongside the estimate, and conclusions must hold across them or
   be labelled sensitive to missing data.

### 6.2 Pre-specified sensitivity analyses

- **Available-pair analysis** (DEC-4): item score from valid pairs only, which assumes data
  are missing at random.
- **Truncation rate by condition.** Truncation can depend on the outcome, since compliant
  answers are longer. If the rate differs between the two conditions of a contrast by more
  than 5 points, that contrast is labelled at risk of truncation bias.
- **Judge disagreement.** Primary estimates recomputed with the second judge's labels on the
  doubly-judged subsample.

## 7. Sample size

[`DESIGN_COMPARISON.md`](DESIGN_COMPARISON.md) simulates power and type I error with
correlated observations: random item intercepts, item-specific random slopes, and a
preamble-only model. It reports the probability-scale estimand each scenario implies. Its
inputs are assumptions, and the pilot must estimate:

- baseline compliance
- item intercept variance
- slope variance
- truncation and exclusion rates

Tier A size is then chosen for at least 80% power for a 10 percentage-point effect at the
worst-case Holm threshold.

## 8. Sampling

- **Primary:** one sample per cell at temperature 0. The seed is set and the provider's model
  fingerprint is recorded.
- **Stability subsample:** a pre-specified 20% of items, 5 samples at T = 0.7, reporting how
  often answers change between samples (DEC-5).

## 9. Judge and validation

- **Blinding:** the judge receives only the item's `core_request` and the response; never the
  cue, pretext, filler, wording or model.
- **Rubric:** `v1-draft` in `safetylens/judge.py`. Rubric versions are hashed into every
  judgment.
- **Human validation (not done):**
  - two raters label a stratified held-out set of about 200 responses
  - rubric changes are allowed only on a separate development set
  - acceptance requires judge–human Cohen's κ ≥ 0.70 on `harmful_compliance`, with
    inter-rater κ reported
  - a second judge from a different model family labels a 20% subsample
- **Misclassification correction (planned):** use the judge's sensitivity and specificity on
  the validation set to report misclassification-corrected estimates (Rogan–Gladen), with
  uncertainty from bootstrapping the validation set.

No claim of judge validity is made until this has been carried out and reported.

## 10. Gates before any paid call

1. Protocol and decisions approved; protocol tagged as frozen.
2. Items written, licence-reviewed and approved by two reviewers (`--require-approved`).
3. Judge validated per §9.
4. Live execution implemented with a preflight call per model (parameters accepted, finish
   reasons returned) and hard budget enforcement. **Neither exists; `safetylens run` refuses
   live providers.**
5. Pilot of about 10% of items on one model, with an approved budget, to estimate the §7
   inputs.
6. Full run, with an approved budget.
