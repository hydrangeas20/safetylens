# Public release audit

**Repository:** `hydrangeas20/safetylens` (private at the time of audit)
**Audit date:** 2026-10-27
**Scope:** every reachable commit, branch, pull-request ref, blob and commit message; PR
artifacts; GitHub Actions metadata; images; licensing. The audit does not stop at the working
tree.

## Verdict: **PASS**, subject to the owner's manual review below

No credentials, personal data beyond the owner's chosen commit identity, raw model output,
unredacted prompts, third-party benchmark text or private-archive history was found anywhere
in reachable history. Nothing found requires rewriting history or a new repository.

The verdict is not a substitute for the manual review in [§6](#6-required-manual-review-before-changing-visibility).
Some surfaces could not be inspected from the audit environment ([§5](#5-what-could-not-be-verified)).

> **Why history matters.** Once public, every reachable object can be fetched, including
> `refs/pull/N/head`, which GitHub keeps after a branch is deleted. Removing content in a later
> commit does not unpublish it. If the release audit ever finds blocking content in history,
> the fix is a new repository with clean history.

## 1. History inventory

| Item | Finding |
|---|---|
| Refs | `refs/heads/main`, `refs/heads/feat/foundation`, `refs/pull/1/head`, `refs/pull/1/merge` (plus this audit's branch and PR once opened) |
| Tags / releases | None |
| Commits | 8 reachable before this branch; **one root commit** (`e28f8a0`, the bootstrap) |
| Commit authors | `hydrangeas20 <hamda@duck.com>` (the owner's chosen identity). GitHub's generated PR merge ref uses `Hamda <168490763+hydrangeas20@users.noreply.github.com>` |
| Unique blobs | 94 (91 text, 3 binary images) |
| Actions artifacts | None |
| Issues, PR comments, reviews | None. PR #1 has a description only |

Reproduce: `safetylens release-audit` (CI runs it on every push with full history). The
counts above describe history before this audit's branch. Later commits are covered by the
CI job, which first failed on this branch and was fixed as described in §3.

## 2. Archive separation

| Check | Result |
|---|---|
| Archive commits (`b1476d1`, `b5d0dba`) present here? | **No.** Different root; no shared commits |
| Archive commit and blob objects present here | 3 of 19, all intentional: `results/stats.csv`, `results/refusal_rates.csv` and `results/divergence_summary.csv`, the original aggregate tables, copied byte-for-byte to `historical/original_outputs/` |
| Raw per-model CSVs, notebook, figures, `prompt_pairs.json` from the archive | **Not present** in any commit |
| Archive prompt text anywhere in history | **0 occurrences** (all 42 eval and deploy prompts searched) |
| Archive response text anywhere in history | **0 occurrences** (415 windows of 60 characters from every non-error response searched) |

Reproduce: `safetylens release-audit --archive <local safetylens-research checkout>`.

## 3. Content checks over every historical blob

| Check | Result |
|---|---|
| API keys and tokens (Anthropic, Groq, OpenAI-style, GitHub, AWS, Slack, Google), private keys | **None real.** The only matches are deliberately constructed fake values in `tests/unit/test_scan.py`, the scanner's own test fixture |
| Email addresses | Only `hamda@duck.com` (the owner's chosen commit address, in `docs/DECISIONS.md`) and no-reply/example addresses |
| Local filesystem paths (`/home/…`, `/Users/…`, `/mnt/…`, sandbox paths) | None |
| CSV columns containing raw text (`prompt`, `response`, …) | None. Redacted files hold `prompt_sha256`, `response_sha256`, lengths and derived flags only |
| JSONL with non-synthetic model output | None (only `[SYNTHETIC-…]` markers) |
| Image metadata (PNG text/EXIF chunks) | None in `assets/safetylens-hero.png` or `docs/diagrams/architecture.png` |
| Hazard terms | Present only in the scanner's own keyword list (`src/safetylens/scan.py`) and its test. They are general-knowledge precursor and component names used for detection, with no quantities or procedures |
| Audit tool's own patterns and fake inputs | `src/safetylens/release_audit.py` contains the path patterns it detects and is path-allowlisted like `scan.py`. The first pushed version of `tests/unit/test_release_audit.py` (blob `e300168`) contains a fabricated email and home path. That exact blob and those two findings are pinned in `REVIEWED_FALSE_POSITIVES`, and later versions build the values at runtime so they stay fully scanned |

## 4. Manual review performed during this audit

- **Judge rationales** (the `reason` column in `historical/redacted/*.csv`): all 84 Llama rows
  were read; the 42 Qwen rows only describe error strings. Every rationale is a one-sentence
  meta-description such as "provides step-by-step meth synthesis information including specific
  precursor chemicals and reaction types". None names a chemical, quantity, step, method,
  stereotype or score. Several reveal that persona framings elicited partial compliance on
  high-severity topics (drug synthesis, explosives, self-harm methods), which is normal content
  for a safety paper.
- **Docs.** `docs/DEFECTS.md` (W9) and `historical/AUDIT.md` describe the *kind* of content in
  the private archive without reproducing it. The unfilled template token `[ethnic group]` is
  quoted as defect evidence.
- **Prompt hashes.** Redacted data stores SHA-256 hashes of the archived prompts. Short prompts
  can be confirmed by guessing, but prompt text is the request, not harmful output.
- **Commit messages and PR description.** Every commit message and the PR #1 description
  contain `Claude-Session: https://claude.ai/code/session_…` links. They point to a private
  session that only the owner can open, and they cannot be removed from PR #1's refs (DEC-11).

## 5. What could not be verified

| Surface | Why | Risk assessment |
|---|---|---|
| GitHub Actions run logs (runs on PR #1, including one failed run) | Log downloads are blocked from the audit environment | Low. Workflows reference no secrets; logs contain test output, synthetic results and audit tables derived from committed files. Owner should skim or delete old runs (§6) |
| Actions secrets, variables, caches; collaborators | API paths blocked from the audit environment | Secrets are masked in logs and never written to the repository; check that none exist that you don't expect |
| Live github.com rendering | No signed-in browser | README checked via the GitHub API, the Mermaid CLI and a headless preview of GitHub's HTML |

## 6. Required manual review before changing visibility

- [ ] **Banner rights.** Confirm you own or have rights to publish `assets/safetylens-hero.png`
      (including any AI-generation tool's terms).
- [ ] **Judge rationales.** Skim `historical/redacted/Llama-3.3-70B.csv` and
      `Llama-3.1-8B.csv`, column `reason`, and confirm you're comfortable publishing them.
- [ ] **Session links.** Decide whether `Claude-Session` links in commit messages and PR
      descriptions are acceptable publicly (they can't be removed from existing PR refs).
- [ ] **Actions logs.** Open the Actions tab and skim one log per job, or delete old workflow
      runs (Actions → run → "Delete workflow run").
- [ ] **Secrets.** Settings → Secrets and variables → Actions: confirm there are none you don't
      expect.
- [ ] **Archive stays private.** Confirm `hydrangeas20/safetylens-research` remains private.
      This repository names it but never links it.
- [ ] **Rendered README.** View the README on github.com (desktop and phone): banner, badges,
      Mermaid diagram.

## 7. Licensing

| Item | Status |
|---|---|
| Project licence | **None** (owner's decision). All rights reserved by default; GitHub's terms still let others view and fork a public repository on GitHub. An MIT `LICENSE` file existed briefly on this branch (commits `52e231a`, `9214d9f`) before removal |
| Runtime dependencies | numpy, pandas, scipy (BSD), pydantic, PyYAML (MIT). Permissive and not vendored |
| Dev and CI tools | pytest, ruff, mypy, coverage, Mermaid CLI (MIT/Apache). Not redistributed. `pathspec` (MPL-2.0) is a transitive dev dependency only |
| Third-party benchmark text | None committed. HarmBench, StrongREJECT and XSTest are only named |
| Model outputs | No raw outputs committed. Aggregates and hashes only. Judge rationales are outputs of an Anthropic model generated by the owner |
| Banner | Owner-supplied; rights to be confirmed (§6) |

## 8. Files that become public

Everything tracked on every branch and PR ref (93 files at the time of audit), plus files
deleted in history (`assets/banner-placeholder.svg`):

| Path | Contents |
|---|---|
| `README.md`, `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `Makefile`, `pyproject.toml`, `uv.lock`, `.gitignore` | Project files |
| `.github/` | CI workflow, PR template, CODEOWNERS |
| `assets/safetylens-hero.png` | Banner |
| `src/safetylens/` | Package source |
| `tests/` | Offline tests |
| `configs/` | Synthetic config; v1 draft config (refused by `run`) |
| `data/synthetic/items.jsonl` | Inert synthetic items |
| `examples/synthetic-demo/` | Synthetic demo output, labelled synthetic |
| `historical/` | Manifest, redacted archive data (hashes, labels, rationales), original aggregate tables, generated audit outputs |
| `docs/` | Protocol, decisions, defects, design comparison, architecture, testing, data policy, item review, this audit, implementation log, diagrams, templates |
| PR #1 and later PR descriptions | Visible on the Pull requests tab |
