# Milestone 05 — Evaluation and safety

Adds isolated answer-key evaluation, adversarial fixtures, public-boundary validation, strict quality/security/package gates, locked dependencies, and Python 3.12/3.13 CI.

## Dependency remediation

- Upgraded the locked development test runner from vulnerable pytest 8.4.2 to
  pytest 9.0.3 in response to `PYSEC-2026-1845`.
- Re-ran the complete release gate and dependency audit after synchronization.
