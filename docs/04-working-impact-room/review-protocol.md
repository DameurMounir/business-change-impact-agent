# Human review protocol

A review command binds the run ID, exact analysis digest, one-time challenge nonce, reviewer and terminal action. Challenges expire, are invalidated when replaced and are consumed once. A stale digest, replay, expired nonce or concurrent terminal action fails closed.

`EDIT` is deliberately narrow: a reviewer may add a note and/or override the attention tier for an existing impact. The reviewer cannot change evidence, entities, path relationships, classification, origin change or authority boundaries.
