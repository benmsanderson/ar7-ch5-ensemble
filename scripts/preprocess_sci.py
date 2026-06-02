"""Preprocess the SCI 2025 ensemble xlsx into analysis-ready CSVs.

Ports scenariocompass `scripts/excel_to_csv.py`. Reads
data/SCI/SCI-2025_v1.0_pathways_ensemble_global.xlsx and writes tidy CSVs
(including the pre-harmonised+infilled driving emissions) to data/sci_csv/.
Implemented in milestone 3/4. See docs/data_setup.md for how to obtain the xlsx.
"""

import sys


def main() -> int:
    raise SystemExit(
        "preprocess_sci is not implemented yet (milestone 3/4). "
        "Place the SCI xlsx per docs/data_setup.md first."
    )


if __name__ == "__main__":
    sys.exit(main())
