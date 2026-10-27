# Data and publication policy

## What may be committed to this repository

| Allowed | Not allowed |
|---|---|
| Redacted historical data (hashes, lengths, derived flags, judge labels and one-sentence reasons) | Raw model responses to harmful requests, from any run |
| Synthetic items and synthetic run outputs (inert `[SYNTHETIC-…]` markers) | API keys, tokens or credentials of any kind |
| Aggregate results, generated reports | Unreviewed excerpts of model output |
| Item metadata. Item text only after the review below | Real tier A item text before licence and hazard review |

- Raw run data goes to `runs/`, which is git-ignored.
- Live cassettes go to `cassettes/live/`, which is also git-ignored.

## Automated checks (`safetylens scan`, run in CI)

1. **Secrets:** patterns for Anthropic, Groq, OpenAI-style, GitHub and AWS keys, and private keys.
2. **Raw-text columns:** any CSV with a `prompt`, `response`, `raw_response`, `text` or
   `completion` column fails.
3. **Unredacted output:** any JSONL record whose `result.text` isn't a synthetic marker or an
   error string fails.
4. **Hazard terms:** a short list of terms suggesting operational detail. Any hit needs human
   review.

These checks are a safety net. They can't recognise every harmful passage.

## Manual review before anything becomes public

- [ ] Every excerpt or example in the README, docs and reports has been read by a person and
      contains no operational detail.
- [ ] Item text has been reviewed for hazard and licence. Benchmark items are referenced by ID
      where the licence doesn't allow redistribution.
- [ ] Judge rationales included in outputs don't restate harmful details.
- [ ] Repository visibility changes are approved explicitly by the owner.

## The historical archive

`hydrangeas20/safetylens-research` contains raw responses with operational detail
([`DEFECTS.md`](DEFECTS.md) W9). It must stay private. Its contents reach this repository only
through `safetylens historical build`, which keeps hashes and derived features and drops raw
text.
