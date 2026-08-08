# Contributing

This repository is a bounded public case study. Contributions must preserve:

- synthetic data only;
- exact evidence traceability;
- deterministic direct and indirect impact semantics;
- human authority for confirmation;
- no go-live, budget, staffing or execution authority;
- no unrestricted graph traversal;
- no answer-key access from runtime code.

Use a focused branch, add or update tests, run `make release-gate`, and describe
claim boundaries in the pull request. Do not force-push shared branches or
commit generated caches, credentials, private documents or production data.
