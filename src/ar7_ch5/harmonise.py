"""Lightweight global emissions harmonisation.

v1 deliberately avoids a full harmonisation/infilling stack (no aneris/silicone
beast): the SCI and ScenarioMIP CMIP7 inputs already ship harmonised and
infilled, so they are used as-is. The one input that genuinely needs
harmonising is SSP2-COM.

This module provides a light-touch GLOBAL (World-total) harmoniser: ratio
convergence for positive-definite species and offset convergence for
zero-crossing species (net CO2, CO2|AFOLU), with a single convergence-year
knob. It anchors to one published historical reference: the CMIP7 world-total
harmonised history (52 species, 1750-2023, Zenodo 17845154).

The same machinery could later re-baseline SCI from its AR6 (~2015) vintage to
the CMIP7 (2023) anchor for cross-ensemble comparability, but that is a
deferred, explicit scientific choice, not a v1 default.

Also the intended home for the harmonisation utility shared with Charlie
Koven's ar7_wg1_ch5 (SSP2-COM construction), with a regression test against his
FaIR outputs (tests/test_harmonise.py).
"""
