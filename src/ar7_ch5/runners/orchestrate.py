"""Run-plan construction and dispatch.

Builds the (scenario, model, config_chunk) run plan and dispatches it via
openscm-runner, with a streaming / chunked output writer so the
SCI x 3-SCM x N-config product does not accumulate in scmdata RAM.

NAC is a raw shared-login node (no SLURM), so worker count is os.cpu_count()
based with a polite cap rather than a queue submission. Respect OMP_NUM_THREADS
if set. See docs/running_on_nac.md.
"""
