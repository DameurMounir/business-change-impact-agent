# Five-minute demonstration script

## 0:00–0:40 — Frame the decision

“This repository answers one question: what changes directly and indirectly when AtlasBridge redesigns applicant onboarding? It does not decide implementation or go-live. The case is fictional, synthetic and fully committed so every claim can be reproduced.”

Show the README preview and the authority statement.

## 0:40–1:25 — Show the evidence model

Open `cases/atlasbridge/change-package.json`, then the entity and relationship files. Explain the eight change components, stable evidence IDs, typed business graph, assumptions, gaps and explicitly unaffected negative controls.

Emphasise that a relationship requires exact evidence; keyword similarity does not create impact.

## 1:25–2:20 — Run the analysis

```bash
uv run business-change-impact-agent analyse \
  --output artifacts/analysis.json \
  --db artifacts/impact-room.sqlite3 \
  --run-id demo-live
```

Show the 36 direct, 12 indirect, three conditional, six unaffected, 22 collisions and five blocked claims. Explain that these are frozen-case observations, not general accuracy.

## 2:20–3:10 — Inspect one trace and one blocked claim

Open the CC-03 path to the external screening service. Point to the four relationship IDs, evidence references, vendor-capacity assumption and evidence gap. Then show the supplier candidate blocked at the fifth edge.

Show `DATA-CASE-STATUS` as a collision reached by accountable ownership, exception handling and notifications but counted once.

## 3:10–4:15 — Demonstrate human authority

Issue a review challenge. First try a stale digest and show the controlled rejection. Then confirm using the exact digest and one-time nonce. Explain expiry, replay protection, concurrency control and the hash-linked event ledger.

## 4:15–4:45 — Export equivalent packets

Generate JSON, Markdown and HTML. Run the equivalence verifier and show the shared snapshot digest. Open the standalone HTML to demonstrate escaped evidence-derived content and no external CDN.

## 4:45–5:00 — Close honestly

“This proves a controlled, evidence-grounded impact-analysis vertical for one synthetic case. It does not prove that all real impacts are known, that conditional gaps are closed, or that the change should go live.”
