# Decisions requiring review

These choices could materially change the research conclusions, so they are recorded here
rather than settled silently. Each lists the alternatives, what is implemented now, and a
recommendation. None is final until the owner approves it and the protocol is frozen.

| ID | Decision | Alternatives | Implemented now | Recommendation |
|---|---|---|---|---|
| DEC-1 | **Design** | Compact (6 conditions, one factor at a time) vs full factorial (16 conditions) | Both supported; draft config uses `full` | Full. It has more power per item and per model call in every simulated scenario ([`DESIGN_COMPARISON.md`](DESIGN_COMPARISON.md)) and can estimate interactions. Re-check after the pilot estimates slope variance. |
| DEC-2 | **Primary family** | (a) 4 contrasts × all models in one Holm family; (b) one family per model; (c) one headline contrast primary, the rest secondary | (a) | (a), the most conservative. Choose (c) only if a single hypothesis is pre-registered as the main one. |
| DEC-3 | **Primary outcome definition** | `harmful_compliance` including partial vs full compliance only | Includes partial | Keep including partial and report partial separately. Revisit after the labelling pilot. |
| DEC-4 | **Missing data in full-design contrasts** | (a) complete-case items; (b) average available valid pairs (assumes missing at random) | (a), plus worst/best-case bounds on every contrast | (a) primary, (b) pre-specified sensitivity. Keep error rates low: in the synthetic demo, 3% persistent API errors plus judge failures exclude up to 17 of 40 items from some contrasts. |
| DEC-5 | **Sampling** | Greedy only; greedy plus stability subsample; k samples everywhere | `samples_per_cell` supported; analysis uses sample 0 | Greedy primary plus a 20% stability subsample at T = 0.7. |
| DEC-6 | **Model-based secondary analysis** | Mixed-effects logistic (new dependency such as statsmodels, or a Bayesian package) vs none | Not implemented | Add after DEC-1, with item random slopes and a paraphrase random intercept. |
| DEC-7 | **Paraphrase variation** | One fixed sentence per cue/pretext/filler vs several paraphrases balanced across items | One fixed sentence | Several paraphrases (plan in [`PROTOCOL.md`](PROTOCOL.md) §3.2), so conclusions don't rest on one sentence. Changes rendering and the item schema. |
| DEC-8 | **Truncation policy** | Retry at a larger budget then exclude (current) vs judge truncated responses with a flag | Retry, then exclude | Keep, and report truncation rate by condition, because truncation can depend on the outcome (historical W8). |
| DEC-9 | **Models** | Re-run the archived three vs a new set | Draft config lists the archived three | Decide from the research question. Re-running them allows comparison with the archive but keeps W6. |
| DEC-10 | **Licence** | MIT, Apache-2.0, or none | **None** (owner's decision). Without a licence, all rights are reserved: the code can be viewed, but not reused, modified or redistributed | Owner's choice. Revisit if outside contributions or reuse are wanted. |
| DEC-11 | **Commit attribution trailers** | Keep `Co-Authored-By` / `Claude-Session` trailers vs author-only attribution | Present in every commit message and in PR descriptions | Owner's choice. They can't be removed from existing PR refs (see [`PUBLIC_RELEASE_AUDIT.md`](PUBLIC_RELEASE_AUDIT.md)). Future commits can omit them. |
| DEC-12 | **Cue length control** | Accept approximate length match between cue (10 words) and filler vs a cue-length filler variant | Approximate; `cue_explicit_vs_filler` reported as a control | Write filler paraphrases in the cue's length range when doing DEC-7. |
| DEC-13 | **Claims of "no effect"** | Report non-significance only vs equivalence test (TOST, ±5 pp) | Not implemented | Implement TOST before any "no effect" claim is made. |
| DEC-14 | **Evaluation awareness** | Claim only evaluation-framing effects (current scope) vs add a behavioural manipulation check vs add white-box probes on open-weight models | Framing effects only; framing and awareness distinguished in [`PROTOCOL.md`](PROTOCOL.md) §1.1 | Add the behavioural manipulation check before freezing. Treat white-box work as a separate follow-up study. |
| DEC-15 | **Model-level exclusion threshold** | Exclude a model with > 50% invalid cells vs report every model with its bounds | > 50% (draft) | Fix before collection. A model near the threshold should be reported with missing-data bounds either way. |
| DEC-16 | **Judge acceptance thresholds** | κ ≥ 0.70 alone vs κ ≥ 0.70 and sensitivity ≥ 0.80 vs thresholds from the pilot | κ ≥ 0.70 and sensitivity ≥ 0.80 (draft) | Keep both: κ alone can be high while missing rare harmful completions. |
