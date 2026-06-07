# Installation

[Pixi](https://pixi.sh) is the single source of truth for the environment, so
authors only learn one tool. It resolves both the conda-forge scientific base
and the pinned upstream openscm-runner engine.

## Quickstart

```bash
# 1. Build the environment (resolves the engine feature branch + climate models).
pixi install

# 2. Drop into the environment (optional; or prefix commands with `pixi run`).
pixi shell

# 3. See the run interface.
pixi run python scripts/run_scenarios.py --help

# 4. Run the tests.
pixi run test

# 5. Run one experiment end-to-end (FaIR-only smoke, ~10 s).
pixi run python scripts/run_scenarios.py \
    --experiment ssp2com --models fair --n-members 5

# 6. Run vetting + feasibility + classification on the SCI ensemble (~5 min).
pixi run python scripts/classify.py --source xlsx

# 7. Compute the emissions archetypes (features -> clusters -> representatives).
pixi run python scripts/compute_archetypes.py

# 8. Build the figures registered in schemes/figures.yaml.
pixi run python scripts/make_figures.py --all
```

## Common tasks

| Task | Command |
| --- | --- |
| Run the test suite | `pixi run test` |
| Lint | `pixi run lint` |
| Format | `pixi run format` |
| Build this site | `pixi run docs` |
| Live-preview this site | `pixi run docs-serve` |

## MAGICC binary

MAGICC needs the path to the licensed binary. It is machine-specific, so it is
**not** hardcoded; set it in your shell or a gitignored `.env.local`:

```bash
export MAGICC_EXECUTABLE_7=/path/to/magicc-dist/magicc7/bin/magicc
```

See [Data setup](data_setup.md) for the full input-data checklist and
[Running on NAC](running_on_nac.md) for the cluster-specific notes (thread
pinning, memory overcommit, batch submission).
