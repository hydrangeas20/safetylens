# Public release audit

**Repository:** `hydrangeas20/safetylens` (private at the time of audit)
**Audit date:** 2026-10-27, after PR #1 was squash-merged into `main` (`f32f80d`)
**Scope:** the current tree; every commit, branch and pull-request ref; every blob and commit
message; GitHub Actions runs, logs and artifacts; images; licensing.

## Verdict: **PASS**

No blocking content was found in the tree or in any reachable history. Making the repository
public is safe once the owner completes the short manual review in §5. Nothing found requires
rewriting history or a new repository.

> **History is permanent once public.** Every reachable object can be fetched, including
> `refs/pull/N/head`, which GitHub keeps after a branch is deleted. If a future audit finds
> blocking content in history, the fix is a new repository with clean history, not a new
> commit.

## 1. Evidence

| Check | Result | How |
|---|---|---|
| Refs audited | `main`, `feat/foundation`, `release/public-readiness`, `refs/pull/1/head`, `refs/pull/2/head`, `refs/pull/2/merge`, plus this PR's branch | Fresh `git clone --mirror` plus `refs/pull/*` |
| Commits and blobs | 12 commits, one root (`e28f8a0`); 137 text blobs and 3 images scanned | `safetylens release-audit` |
| Secrets (API keys, tokens, private keys) | **None real.** The only matches are constructed fake keys in the scanner's own tests | Same |
| Personal data | Only the owner's chosen commit email and GitHub's no-reply address (display name "Hamda" on the squash-merge commit) | Same |
| Local paths, image metadata | None in repository content; no PNG text/EXIF chunks | Same, plus a PNG chunk check |
| Raw model output | None. CSVs hold hashes, lengths, labels and one-sentence judge rationales; JSONL holds only `[SYNTHETIC-…]` markers | Same, plus manual reading of all 84 Llama rationales |
| Archive history | **No archive commits.** 3 of 19 archive commit/blob objects are present, all intentional: the aggregate tables `stats.csv`, `refusal_rates.csv`, `divergence_summary.csv` | `release-audit --archive` |
| Archive prompts and responses | 0 of 42 prompts and 0 of 415 sampled response windows found anywhere in history | Text search over every historical blob |
| Third-party benchmark text | None committed (benchmarks are only named) | Manual review |
| Licensing | No project licence (owner's decision, DEC-10): all rights reserved. Dependencies are permissive and not vendored | Package metadata |

Reproduce: `uv run safetylens release-audit --archive <local safetylens-research checkout>`.
CI runs the history audit on every push.

## 2. GitHub Actions

| Item | Finding |
|---|---|
| Runs | 9 (7 success, 2 failure) on `feat/foundation`, `main` and `release/public-readiness` |
| Artifacts | **0.** The workflow uploads none |
| Secrets and caches | The workflow references no secrets and uses no caches |
| Logs | Could not be downloaded from the audit environment. Instead, every CI job's commands were rerun locally and their full output (107 lines) was scanned with the same checks |
| Log content | Tool output, test results, coverage, synthetic results, the historical flag table, and the release audit's report lines. That includes the session link it reports for review, and in failed run 40547470044 the audit tool's own regex patterns and fabricated test values. No secrets, personal data or model output |
| Runner paths | Logs contain GitHub's generic runner workspace paths, which are not personal |

## 3. Items reviewed and accepted (not blocking)

- **Judge rationales** in `historical/redacted/*.csv`: meta-descriptions only, no operational
  detail. Several say that persona framings got partial compliance on high-severity topics.
- **Session links:** every commit message (including the squash commit on `main`) and the PR
  descriptions contain a `Claude-Session` link. It opens only for the owner's account, and it
  cannot be removed from existing refs (DEC-11).
- **Scanner keyword list:** `src/safetylens/scan.py` lists general precursor and component
  names for detection, with no quantities or procedures.
- **Reviewed false positive:** blob `e300168` (first version of the release-audit tests)
  contains a fabricated email and home path. It is pinned by exact blob ID in
  `REVIEWED_FALSE_POSITIVES`.
- **Former MIT licence:** an MIT `LICENSE` existed briefly on `release/public-readiness`
  (`52e231a`, `9214d9f`) and was removed. The repository has never been public, so no licence
  was ever offered, but those commits will be visible once it is.

## 4. Not verifiable from the audit environment

- Raw Actions log files (reconstructed as described in §2).
- The secrets/variables settings page.
- The live github.com rendering. It was checked through the GitHub API, the Mermaid CLI and a
  headless preview of GitHub's HTML.

## 5. Owner checklist before changing visibility

- [ ] Confirm you have the rights to publish `assets/safetylens-hero.png`.
- [ ] Skim the `reason` column of `historical/redacted/Llama-*.csv`.
- [ ] Accept the session links in commit messages and PR descriptions, or start a fresh
      repository if they must not be public.
- [ ] Settings → Secrets and variables: confirm nothing unexpected.
- [ ] Optionally delete old workflow runs (Actions → run → Delete workflow run).
- [ ] Keep `hydrangeas20/safetylens-research` private.
- [ ] After merging, run `uv run safetylens release-audit` on `main`: 0 blocking findings.
- [ ] After going public, view the README logged-out on desktop and phone.
