# Harmonisation

Chapter-owned harmonisation + infilling pipeline. One pipeline serves
SCI, ScenarioMIP CMIP7 and SSP2-COM; per-ensemble specialisation lives
in the raw loaders. See
[harmonisation open questions](../harmonisation_open_questions.md)
for the scientific choices the pipeline encodes (history anchor, aneris
overrides, infilling DB, infiller method, Halon strip, etc.).

## Pipeline

::: ar7_ch5.harmonisation

## CMIP7 inputs

The four input files (history, aneris overrides, infilling DB, GHG
inversions) loaded by the harmoniser.

::: ar7_ch5.cmip7_inputs
