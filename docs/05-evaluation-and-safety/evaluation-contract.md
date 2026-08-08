# Evaluation contract

The evaluator alone reads `evaluation/answer-key.json`. Runtime source and distributions may not contain or reference the key. Metrics report exact agreement for direct, indirect, conditional and explicitly unaffected sets on the frozen synthetic case, path/evidence validity, adversarial block coverage and deterministic summary agreement.

A perfect frozen-case score means that the committed rules reproduce the committed human-curated answer key. It is not general accuracy, production completeness or evidence that every real-world impact has been discovered. Live-model evaluation remains `NOT_RUN`.
