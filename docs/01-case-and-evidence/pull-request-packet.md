# M01 pull-request packet

## Scope

Freeze the synthetic change package, exact evidence statements, typed graph,
negative controls, deliberate evidence gaps, manifest and evaluator-only answer
key.

## Non-scope

No propagation engine, review workflow, interface, model provider, go-live
decision or external change execution.

## Verification

```bash
python scripts/build_case.py --check
python scripts/verify_case.py
python -m pytest tests/test_case_contract.py --no-cov
```
