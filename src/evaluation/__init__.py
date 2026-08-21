"""Post-hoc diagnostics helpers.

Per-step readiness/counters/flags live in `src.evaluation.diagnostics`. The
v1 extraction-accuracy evaluation (`helpers.py`, SignalDoc-vs-MethodSpec
scoring) was retired along with `MethodSpec`/`SemanticExtractor`;
`load_signaldoc` moved to `src.infra.reference` (its only remaining
consumer).
"""
