# Running the SCMs

`scripts/run_scenarios.py` drives the climate models through the openscm-runner
engine for a chosen experiment and SCM set, writing per-experiment ensemble
NetCDFs under `outputs/<experiment>/<scm>/`.

```bash
pixi run python scripts/run_scenarios.py --help
pixi run python scripts/run_scenarios.py \
    --experiment ssp2com --models fair --n-members 5
```

## The three-CLI chain

The command-line tools form a chain; each is read-only on the layer below it:

```
scripts/cache_status.py        reports which ensemble outputs / CSVs are present
scripts/run_scenarios.py       produces SCM ensemble NetCDFs (per experiment)
scripts/classify.py            produces classification CSVs (per source)
scripts/compute_archetypes.py  produces archetype features / clusters / picks
scripts/make_figures.py        reads the cached outputs, writes PNG / PDF
```

`cache_status.py` is the entry point for "what do I need to run before this
figure works?". For every (experiment, SCM) it lists present / expected counts
and prints the exact `run_scenarios.py` command beside each missing piece.
`make_figures.py` calls into the same enumerator and fails early with a clear
`FileNotFoundError` if a required input is missing, so iteration stays fast and
the figure layer never silently runs an SCM.

## How emissions reach the models

Three of the four input sets arrive already harmonised and infilled, so this
repository does not carry a harmonisation/infilling stack:

- **SCI** ships SCM-ready driving emissions
  (`Climate Assessment|Infilled|Emissions|*`).
- **ScenarioMIP CMIP7** is harmonised by the CMIP7 pipeline.
- **SSP2-COM** is the only set harmonised here, by a light global harmoniser
  anchored to a published 2023 history (see
  [`ar7_ch5.harmonise`](../reference/harmonise.md)).

See [Methods](../methods.md) for the harmonisation details and the SCI-vintage
caveat, and the [Engine / upstream switch](../engine_upstream_switch.md) page
for how chapter pathway IDs map onto canonical RCMIP3 scenario names.

## The Chapter 5 contribution

SCI ships MAGICC-only climate outcomes. The value added here is running the
same harmonised emissions through FaIR 2.x and CICERO-SCM as well, giving a
genuine three-SCM ensemble spread on identical inputs.
