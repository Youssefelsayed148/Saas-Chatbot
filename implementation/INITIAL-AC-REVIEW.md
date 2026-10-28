# Independent initial A / C-partial review — 2026-10-28

Reviewer: read-only subagent `/root/review_initial_ac`, separate from all
implementation workers. The lead recorded its returned findings here.

The reviewer checked code, diffs, harness isolation and retained test evidence.
It did not rerun suites, modify files, or execute live operations.

| Scope | Independently verified result |
| --- | --- |
| A1 | JUnit: 418 tests, zero failures/errors/skips |
| A2–A4 | Reconstructed four JUnit attempts and summary.json: 66 distinct cases pass in their latest execution; not one green 66-case run |
| A6/A7 | JUnit: 25 tests, zero failures/errors/skips; final canary unittest log: 20 passed |
| C1/C3 | Six source checks passed; key passthrough reaches API/worker; backup failure aborts before build/up |

The reviewer found one medium A2 defect: schema-expression normalization folded
quoted SQL literal case and could mistake `'ARRAY'` for `'array'`. The worker
fixed normalization to preserve literals and added a real migration rejection
regression. The reviewer rechecked the correction and independently verified
`'array'`, `'ARRAY'`, and `'ar::textray'` remain distinct. The finding is resolved.

Final review found no remaining blocking/high/medium issues in the reviewed
A2–A4/A6–A7/C1/C3 changes. It confirmed hard-delete workspace authorization,
dependent-row cleanup and preservation of unrelated accounts/raw webhook entries;
fixture repairs retain substantive assertions. Raw forwarding headers are ignored,
verify-token comparison uses UTF-8 bytes, and test Redis/PostgreSQL are private
with external networking disabled during execution.

Limits: A5 is unresolved (official Meta documentation inaccessible); D5 is OPEN
at the owner's request. Full integrated suites, runtime ingress/Compose, backup
restoration, deployment, staging migrations and live canary are UNVERIFIED.
Account hard-delete does not claim remote SaaS erasure; in-flight worker races
and historical audit retention are outside the A4 proof. A16/B1–B4/C2/C4/C5
implementation is not certified by this initial review.

Worker commits integrated locally: Many `afb604f`, `6e80eaa`; SaaS `3347a02`.
Initial integration heads: Many `closeout/batch-a` at `0ca1c67`, SaaS
`closeout/batch-c` at `216a4f0`. No push or main merge.
