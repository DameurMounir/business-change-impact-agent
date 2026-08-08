# Threat model

Controls cover graph injection, prompt-like evidence, unknown entities, unknown relationships, reverse traversal, missing evidence, depth overflow, cycles, evaluator-only identifiers and authority escalation. Evidence text is data and is never executed as an instruction. Runtime code has no evaluator answer-key dependency and no external-effect adapter.
