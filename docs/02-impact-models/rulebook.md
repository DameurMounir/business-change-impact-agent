# Propagation rulebook

`design/propagation-rules.json` is the only source of indirect traversal authority. Each rule fixes the relationship type, forward direction, allowed depth, condition handling and reason code. The case and rulebook both publish a maximum of four edges from the originating change component.

Canonical selection prefers an unconditional path, then the shortest path, then lexical relationship and node identifiers. This makes repeated runs byte-stable and prevents alternative paths from multiplying impact counts.
