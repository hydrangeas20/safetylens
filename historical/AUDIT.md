# Historical audit summary

**Status: historical, exploratory and not validated.** Nothing here is a research finding of
this repository.

- **Archive:** `hydrangeas20/safetylens-research` @ `b5d0dba906b2d6bbeb0bdfc0cbc958079e8ac3cc`
  (private, unmodified). Every archive file is pinned by SHA-256 in [`MANIFEST.json`](MANIFEST.json).
- **What's committed here:** redacted per-model data (`redacted/`, no raw text), the original
  aggregate tables (`original_outputs/`), generated row flags (`row_flags.csv`) and generated
  outputs (`outputs/`). Regenerate everything with `safetylens historical audit`. Verify hashes
  with `safetylens historical verify`.
- **Defects:** listed with evidence in [`docs/DEFECTS.md`](../docs/DEFECTS.md).

## Two separate outputs

| Output | What it is | Use |
|---|---|---|
| [`outputs/historical_reproduction/`](outputs/historical_reproduction/) | The original notebook calculations re-implemented faithfully, defects included. They match the archived `stats.csv`, `refusal_rates.csv` and `divergence_summary.csv` to 1e-9 (`comparison.json`). | Proves the archive was read the same way the original analysis read it. **Not findings.** |
| [`outputs/exploratory_corrected/`](outputs/exploratory_corrected/report.md) | Corrected statistics: valid denominators, complete pairs, exact McNemar, Wilcoxon, d_z, bootstrap CIs, Holm correction, Qwen excluded. | Exploratory description of the archived run. **Still confounded (W1, W2) and not validated.** |

## Claims in the archived README and report, checked against the records

| Archived claim | Supported by the records? |
|---|---|
| Qwen3-32B shows no meaningful eval–deployment divergence. | **No.** There are no Qwen3-32B model responses: 42/42 rows are API errors (D1). |
| Qwen3-32B is "framing-insensitive and uniformly permissive". | **No.** Same reason. |
| Both Llama models show statistically significant divergence (README). | **Not as computed.** The original test was unpaired and uncorrected (D4, D5). Under the corrected paired analysis, both Llama models show lower refusal and lower safety scores in the deploy prompts, with Holm-adjusted p < 0.05 within the 4-test exploratory family. This describes the archived prompts only. The deploy prompts add personas and justifications (W1), some are arguably legitimate requests (W2), and the result depends heavily on possibly-truncated responses (W8). So it does **not** show that evaluation framing changes safety behaviour. |
| Refusal drops 55.6 percentage points under deployment framing. | **Overstated.** Failed judgments were counted as non-refusals (D2). With valid denominators and complete pairs the paired differences are 0.500 (Llama-3.1-8B, 14 pairs) and 0.625 (Llama-3.3-70B, 16 pairs), with wide CIs and the same caveats. |
| Model scale does not reduce the divergence gap. | **Not testable** with these data (W6). |
| Harmful-content and privacy prompts drive the largest divergence. | **Descriptive only.** 0–5 valid pairs per category; no inference possible (W5). |
| Llama-3.1-8B is less cautious on self-harm under eval framing. | **Descriptive only**, 2 pairs. |

## What the archive can still be used for

- The genuine Llama responses can serve as development material for the judge rubric and the
  item set, provided raw text stays inside the private archive.
- The defect list is the requirements list for the new pipeline. Each defect has a check in
  this repository.
