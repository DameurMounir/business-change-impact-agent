# Impact semantics

The repository uses four mutually exclusive result classes:

- **DIRECT** — an authorised change component has an explicit direct-change relationship to the entity.
- **INDIRECT** — a canonical forward path continues from a direct entity through only published propagation rules, within four total edges from the change component, with evidence on every edge.
- **CONDITIONAL** — the same path controls hold, but at least one relationship carries an assumption or unresolved evidence gap.
- **EXPLICITLY_UNAFFECTED** — the change package and evidence explicitly identify a negative-control entity as outside scope.

No keyword match, document co-location, generic association, implicit reversal or unrestricted traversal creates an impact.
