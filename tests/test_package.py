"""Smoke test that the package imports and its public modules are present.

The substantive tests (loaders, vetting, classification, runner smoke tests,
SSP2-COM harmonisation regression vs Charlie Koven's FaIR output) arrive with
their respective milestones. This one keeps CI meaningful from the scaffold on.
"""

import importlib

import ar7_ch5


def test_version():
    assert ar7_ch5.__version__


def test_modules_importable():
    for name in [
        "ar7_ch5.load",
        "ar7_ch5.harmonisation",
        "ar7_ch5.cmip7_inputs",
        "ar7_ch5.vetting",
        "ar7_ch5.classification",
        "ar7_ch5.runners.fair",
        "ar7_ch5.runners.ciceroscm",
        "ar7_ch5.runners.magicc",
        "ar7_ch5.runners.orchestrate",
        "ar7_ch5.experiments.sci_ensemble",
    ]:
        importlib.import_module(name)
