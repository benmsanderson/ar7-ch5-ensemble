"""Retired: SSP2-COM validation against Charlie Koven's legacy harmoniser.

This script compared the chapter's old light-convergence SSP2-COM
harmoniser (`ar7_ch5.harmonise`) against Charlie's pipeline. Both have
been superseded:

* the chapter no longer runs SSP2-COM through a one-off light convergence
  harmoniser; it goes through the same
  ``gcages.cmip7_scenariomip``-backed pipeline as SCI and ScenarioMIP
  CMIP7 (see ``scripts/harmonise.py --ensemble ssp2com``);
* the validation reference is now ``scripts/validate_sci_vs_shipped.py``,
  which compares the chapter pipeline against SCI's shipped
  ``Climate Assessment|Infilled|*`` namespace.

If the chapter still wants a comparison against Charlie's pipeline, that
should be a fresh script that loads both the new chapter cache parquet
and Charlie's csv and computes per-species deltas -- not this stub.
"""

import sys


def main() -> int:
    print(
        "validate_ssp2com_vs_charlie.py is retired -- see module docstring "
        "for the replacement validation entry point.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
