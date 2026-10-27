# Historical data: corrected exploratory re-analysis

> **Generated file - do not edit.** Regenerate with `safetylens historical audit`.
>
> **EXPLORATORY RE-ANALYSIS OF HISTORICAL DATA - NOT VALIDATED. Design confounds wording with persona/pretext; refusal labels contestable; single judge without human validation.**

Source: historical/redacted (derived from safetylens-research @ b5d0dba). Comparison: eval minus deploy, paired by prompt_id, harmful prompts only.

## Data validity

| Model | Rows | API-error rows | Judge failures | Likely truncated (heuristic) | Placeholder prompt | Valid rows |
|---|---:|---:|---:|---:|---:|---:|
| Llama-3.1-8B | 42 | 0 | 6 | 19 | 2 | 36 |
| Llama-3.3-70B | 42 | 0 | 3 | 24 | 2 | 39 |
| Qwen3-32B | 42 | 42 | 0 | 0 | 2 | 0 |

Finish reasons were not recorded for any archived row.

## Excluded models

- **Qwen3-32B**: excluded from all quantitative results: no valid observations ({'model_api_error': 42})

## Paired eval-vs-deploy comparisons (harmful prompts)

Holm correction across a family of 4 tests (Llama-3.1-8B:refused, Llama-3.1-8B:safety_score, Llama-3.3-70B:refused, Llama-3.3-70B:safety_score), alpha = 0.05. Bootstrap: 10000 resamples, seed 20260614.

### Refusal (exact McNemar)

| Model | Pairs | Excluded | Eval rate | Deploy rate | Difference | 95% CI | b / c | p | p (Holm) |
|---|---:|---|---:|---:|---:|---|---|---:|---:|
| Llama-3.1-8B | 14 | {'judge_failed': 4} | 0.857 | 0.357 | 0.500 | [0.214, 0.786] | 7 / 0 | 0.0156 | 0.0419 |
| Llama-3.3-70B | 16 | {'judge_failed': 2} | 0.750 | 0.125 | 0.625 | [0.375, 0.875] | 10 / 0 | 0.0020 | 0.0078 |

### Safety score 1-10 (Wilcoxon signed-rank)

| Model | Pairs | Excluded | Eval mean | Deploy mean | Mean diff | 95% CI | d_z | p | p (Holm) | paired-t p |
|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|
| Llama-3.1-8B | 14 | {'judge_failed': 4} | 9.143 | 6.643 | 2.500 | [0.714, 4.071] | 0.758 | 0.0140 | 0.0419 | 0.0140 |
| Llama-3.3-70B | 16 | {'judge_failed': 2} | 8.750 | 6.562 | 2.188 | [0.500, 3.812] | 0.617 | 0.0189 | 0.0419 | 0.0261 |

### Sensitivity: excluding pairs flagged by the truncation heuristic

| Model | Outcome | Pairs | Difference | p (uncorrected) |
|---|---|---:|---:|---:|
| Llama-3.1-8B | refusal | 6 | 0.167 | 1.0000 |
| Llama-3.1-8B | safety score | 6 | 2.667 | 0.0312 |
| Llama-3.3-70B | refusal | 3 | 0.333 | 1.0000 |
| Llama-3.3-70B | safety score | 3 | -0.333 | 1.0000 |

## Category means (descriptive only; 1-5 pairs per cell, no tests)

| Model | Category | Valid pairs | Mean diff (eval - deploy) |
|---|---|---:|---:|
| Llama-3.1-8B | bias_discrimination | 4 | 3.25 |
| Llama-3.1-8B | harmful_content | 5 | 3.40 |
| Llama-3.1-8B | misinformation | 0 | n/a |
| Llama-3.1-8B | privacy | 3 | 3.33 |
| Llama-3.1-8B | self_harm | 2 | -2.50 |
| Llama-3.3-70B | bias_discrimination | 5 | 1.00 |
| Llama-3.3-70B | harmful_content | 5 | 4.00 |
| Llama-3.3-70B | misinformation | 1 | 3.00 |
| Llama-3.3-70B | privacy | 3 | 2.33 |
| Llama-3.3-70B | self_harm | 2 | 0.00 |

## Safe controls (descriptive)

| Model | Condition | Valid | Refused |
|---|---|---:|---:|
| Llama-3.1-8B | eval | 2 | 0 |
| Llama-3.1-8B | deploy | 3 | 0 |
| Llama-3.3-70B | eval | 3 | 0 |
| Llama-3.3-70B | deploy | 3 | 0 |

## How to read this

- These numbers describe the archived run only. The deploy prompts add personas and justifications, so a difference cannot be attributed to evaluation framing.
- Several deploy prompts are requests where helping is arguably correct; lower refusal there is not necessarily less safe.
- The judge (claude-sonnet-4-6) saw the full framed prompt and was not validated against human labels.
