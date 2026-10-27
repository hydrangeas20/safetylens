# Security and responsible disclosure

## Reporting

Please report security issues privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
("Report a vulnerability" on the repository's Security tab). Don't open a public issue.

Report privately if you find:

- a credential, token or personal data anywhere in the repository or its history
- raw model output with operational harmful content, or text that would let someone
  reconstruct it
- a way to make SafetyLens issue live (paid) API calls without the explicit opt-in described
  below
- a flaw in the redaction or release-audit checks that would let unsafe content through

## Safety properties the code is meant to guarantee

- **No live calls by default.** Live providers need `allow_live: true` in the config *and*
  `SAFETYLENS_ALLOW_LIVE=1`, and `safetylens run` currently refuses live providers outright.
  CI references no secrets.
- **No raw harmful output in the repository.** Historical data is reduced to hashes and
  derived features. `safetylens scan` and `safetylens release-audit` (every blob and commit
  message in history) run in CI.
- **Failures are never data.** API errors, error text, truncation and unparseable judge output
  are recorded as failures and excluded from every statistic.

## Scope

SafetyLens is research software for measuring model behaviour. It is not a content filter and
gives no guarantee about the safety of any model it evaluates.
