# Controlled analysis architecture

The provider-neutral adapter may propose a result, but it cannot create authority. `ImpactAnalysisService` validates the frozen case, loads the committed rulebook, runs the adapter and then verifies the complete result against the evidence-authoritative deterministic graph computation. Malformed, incomplete or divergent adapter output fails closed.

The default `RuleAdapter` uses no network, model or external service. `FixtureAdapter` exists only to test the verification boundary.
