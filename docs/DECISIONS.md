# Decisions requiring review

These choices could materially change the research conclusions, so they were not settled
during implementation. Each entry lists the alternatives, what is implemented now, and a
recommendation. None is final until approved.

| ID | Decision | Alternatives | Implemented now | Recommendation |
|---|---|---|---|---|
| DEC-1 | **Design** | Compact (5 conditions, one factor at a time) vs full factorial (12) | Both supported. The draft config uses `full`. | Full, provided the pilot doesn't show strong within-item slope variation. See `DESIGN_COMPARISON.md`. The estimand differs if interactions exist, so this must be decided before freezing. |
| DEC-2 | **Primary family** | (a) 4 contrasts × all models in one Holm family; (b) one family per model; (c) a single headline contrast as primary, the rest secondary | (a) | (a) is the most conservative. Choose (c) only if one effect is the main hypothesis, e.g. the pretext effect. |
| DEC-3 | **Primary outcome definition** | `harmful_compliance` including partial compliance (current rubric) vs full compliance only | Includes partial | Keep including partial; report partial separately. Revisit after the human labelling pilot. |
| DEC-4 | **Missing-data rule for full-design contrasts** | (a) complete-case per item (all matched pairs valid); (b) average the available valid pairs (assumes missing at random) | (a) | (a) for primary, (b) as sensitivity. In the synthetic run with 3% persistent API errors, (a) dropped 14 of 40 items on some contrasts, so error rates must be kept low. Best/worst-case bounds are specified but not automated. |
| DEC-5 | **Sampling** | Greedy only vs greedy plus stability subsample vs k samples everywhere | Supports `samples_per_cell`; analysis uses sample 0 | Greedy primary, plus a 20% stability subsample at T = 0.7. |
| DEC-6 | **Model-based secondary analysis** | Mixed-effects logistic regression (needs a new dependency such as statsmodels, or a Bayesian package) vs none | Not implemented | Add after DEC-1 is settled. |
| DEC-7 | **Cue wording** | Single fixed cue sentence vs several paraphrases | One sentence (`cue-v1-draft`) | Several paraphrases (cue becomes a random factor), to avoid conclusions that depend on one sentence. Changes item rendering. |
| DEC-8 | **Truncation policy** | Retry at a larger budget then exclude (current) vs judge truncated responses with a flag | Retry, then exclude | Keep. Report the truncation rate per condition, because truncation can depend on the outcome (see the historical W8 sensitivity result). |
| DEC-9 | **Models** | Re-run the archived three models vs a new set | Draft config lists the archived three | Decide based on the research question. Re-running the archived three enables comparison with the history but inherits W6. |
| DEC-10 | **Licence** | e.g. MIT (code) + CC BY 4.0 (docs/data), or no licence while private | No licence file | Owner's choice. Must be settled before any public release. |
| DEC-11 | **Commit attribution trailers** | Keep `Co-Authored-By: Claude` trailers vs author-only attribution to hydrangeas20 | Commits authored as `hydrangeas20 <hamda@duck.com>` with session trailers | Owner's choice. Trailers can be dropped when squash-merging. |
