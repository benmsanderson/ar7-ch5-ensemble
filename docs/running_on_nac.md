# Running on NAC

NAC is the workhorse machine for the large runs.

## Hardware

Single node, AMD EPYC 7742, 2 sockets x 64 physical cores (128 physical, 256
logical with SMT), 2 TB RAM, 2 TB swap. NUMA: node0 = cores 0-63, 128-191;
node1 = cores 64-127, 192-255.

## Scheduling

NAC is a raw shared-login node: there is no SLURM queue. The orchestrator sizes
its worker pool from `os.cpu_count()` with a polite cap rather than submitting
jobs, because the node is shared. Respect `OMP_NUM_THREADS` if it is set in your
environment. NUMA-aware pinning is not pursued in v1.

## Memory and output

2 TB RAM means scenario-level memory pressure is unlikely, but the run output
(SCI x 3 SCMs x N configs) is large, so the orchestrator streams chunked output
to disk rather than accumulating everything in scmdata in RAM. Output goes to a
gitignored `outputs/` directory.

## Environment

Build the environment once with `pixi install`, then `pixi shell` or
`pixi run ...`. The MAGICC binary is staged outside the repo; see
`docs/data_setup.md`.
