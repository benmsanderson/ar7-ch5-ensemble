"""SCM run wrappers and orchestration.

Thin, per-model configuration wrappers around the openscm-runner engine (FaIR
2.x, CICERO-SCM 2.1.0, MAGICC), plus orchestrate.py which builds the
(scenario, model, config) run plan and dispatches it. No mocking of the SCMs:
tests hit the real adapters on small inputs.
"""
