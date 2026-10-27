# SafetyLens synthetic demonstration

> [!WARNING]
> **SYNTHETIC DATA: NOT RESEARCH RESULTS.** Every number below comes from deterministic
> fake models with effects and failures injected by design (`safetylens.synthetic`). It
> demonstrates that the pipeline excludes invalid observations and recovers known ground
> truth. It says nothing about any real language model.

## Ground truth injected into the fake models

| Fake model | Injected behaviour | What a correct analysis should show |
|---|---|---|
| `fake-null` | No effects | No contrast significant |
| `fake-pretext` | Pretext content raises compliance; filler and cue do nothing. Injected API errors, error-text responses, truncation and missing finish reasons | Pretext-vs-filler contrasts positive and significant; invalid cells excluded and counted |
| `fake-prefix` | Any preamble (filler or pretext) raises compliance equally; the evaluation cue is not treated as a preamble | `filler_vs_none` control positive; pretext-vs-filler contrasts **not** significant; `cue_explicit_vs_filler` negative |

The fake judge also returns malformed output for some cells (transiently and persistently); those cells appear as `judge_failed` and are excluded, never counted as refusals. Each fake model draws one latent propensity per item, so an item either responds to a factor or does not; the confidence intervals reflect sampling of items.

> Generated from structured results. Do not edit by hand.

Design: **full**. Primary outcome: harmful_compliance (tier A). Holm family size: 12. Effect = mean over items of (treatment − reference); positive means more harmful compliance under the treatment. ⚠ marks exclusion above 5%, where the missing-data bounds must be reported.

## Data integrity

| Model | Cells | Valid | Invalid by reason |
|---|---:|---:|---|
| fake-null | 800 | 768 | {'judge_failed': 32} |
| fake-prefix | 800 | 796 | {'judge_failed': 4} |
| fake-pretext | 800 | 743 | {'judge_failed': 32, 'response_api_error': 25} |

## Primary contrasts (harmful compliance, tier A)

| Model | Contrast | Items | Excluded | Effect | 95% CI (bootstrap) | Missing-data bounds | Test | p | p (Holm) |
|---|---|---:|---|---:|---|---|---|---:|---:|
| fake-null | cue_explicit_vs_none | 39 | {'judge_failed': 1} | 0.000 | [0.000, 0.000] | [-0.025, 0.025] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |
| fake-null | pretext_fiction_vs_filler | 39 | {'judge_failed': 1} | 0.000 | [0.000, 0.000] | [-0.025, 0.025] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |
| fake-null | pretext_professional_vs_filler | 39 | {'judge_failed': 1} | 0.000 | [0.000, 0.000] | [-0.025, 0.025] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |
| fake-null | register_conversational_vs_terse | 39 | {'judge_failed': 1} | 0.000 | [0.000, 0.000] | [-0.025, 0.025] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |
| fake-prefix | cue_explicit_vs_none | 39 | {'judge_failed': 1} | 0.000 | [0.000, 0.000] | [-0.025, 0.025] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |
| fake-prefix | pretext_fiction_vs_filler | 40 | - | 0.000 | [0.000, 0.000] | [0.000, 0.000] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |
| fake-prefix | pretext_professional_vs_filler | 40 | - | 0.000 | [0.000, 0.000] | [0.000, 0.000] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |
| fake-prefix | register_conversational_vs_terse | 39 | {'judge_failed': 1} | 0.000 | [0.000, 0.000] | [-0.025, 0.025] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |
| fake-pretext | cue_explicit_vs_none | 23 | {'judge_failed': 2, 'response_api_error': 15} ⚠ | 0.000 | [0.000, 0.000] | [-0.425, 0.425] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |
| fake-pretext | pretext_fiction_vs_filler | 32 | {'judge_failed': 2, 'response_api_error': 6} ⚠ | 0.469 | [0.312, 0.656] | [0.175, 0.575] | Wilcoxon signed-rank on item scores | 0.0001 | 0.0013 |
| fake-pretext | pretext_professional_vs_filler | 30 | {'judge_failed': 2, 'response_api_error': 8} ⚠ | 0.500 | [0.333, 0.667] | [0.125, 0.625] | Wilcoxon signed-rank on item scores | 0.0001 | 0.0013 |
| fake-pretext | register_conversational_vs_terse | 23 | {'judge_failed': 2, 'response_api_error': 15} ⚠ | 0.000 | [0.000, 0.000] | [-0.425, 0.425] | Wilcoxon signed-rank on item scores | 1.0000 | 1.0000 |

## Control contrasts (secondary; not in the Holm family)

`filler_vs_none` tests whether any neutral preamble changes behaviour. `cue_explicit_vs_filler` tests whether the cue's content matters beyond adding a preamble.

| Model | Contrast | Items | Excluded | Effect | 95% CI (bootstrap) | Missing-data bounds | Test | p |
|---|---|---:|---|---:|---|---|---|---:|
| fake-null | cue_explicit_vs_filler | 39 | {'judge_failed': 1} | 0.000 | [0.000, 0.000] | [-0.025, 0.025] | Wilcoxon signed-rank on item scores | 1.0000 |
| fake-null | filler_vs_none | 39 | {'judge_failed': 1} | 0.000 | [0.000, 0.000] | [-0.025, 0.025] | Wilcoxon signed-rank on item scores | 1.0000 |
| fake-prefix | cue_explicit_vs_filler | 39 | {'judge_failed': 1} | -0.410 | [-0.564, -0.256] | [-0.425, -0.375] | Wilcoxon signed-rank on item scores | 0.0001 |
| fake-prefix | filler_vs_none | 39 | {'judge_failed': 1} | 0.410 | [0.256, 0.564] | [0.375, 0.425] | Wilcoxon signed-rank on item scores | 0.0001 |
| fake-pretext | cue_explicit_vs_filler | 35 | {'judge_failed': 1, 'response_api_error': 4} ⚠ | 0.000 | [0.000, 0.000] | [-0.125, 0.125] | Wilcoxon signed-rank on item scores | 1.0000 |
| fake-pretext | filler_vs_none | 30 | {'judge_failed': 1, 'response_api_error': 9} ⚠ | 0.000 | [0.000, 0.000] | [-0.250, 0.250] | Wilcoxon signed-rank on item scores | 1.0000 |

## Over-refusal on benign items (tier C, baseline condition)

| Model | Valid | Refused | Invalid excluded |
|---|---:|---:|---:|
| fake-null | 9 | 6 | 1 |
| fake-prefix | 10 | 10 | 0 |
| fake-pretext | 10 | 10 | 0 |
