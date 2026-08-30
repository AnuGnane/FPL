"""v7b Q3: emit one composite-σ asset per floor.

    .venv/bin/python scripts/v7b_composite.py \\
        reports/scenario_noise_estimation.json 0.6

Writes ``reports/scenario_noise_composite_<floor>.json`` through the shipped
``write_noise`` validator, so a table that would be refused at serve time is
refused here instead of three hours into a replay. The estimation asset is
read from ``reports/`` rather than the packaged asset path on purpose: this
cycle writes no assets into ``src/gaffer/assets/``.
"""

import json
import sys
from pathlib import Path

from gaffer.calibrate_noise import composite_table, write_noise


def main(argv: list[str]) -> Path:
    src, floor = Path(argv[0]), float(argv[1])
    payload = composite_table(json.loads(src.read_text()), floor)
    dest = Path("reports") / f"scenario_noise_composite_{argv[1]}.json"
    out = write_noise(payload, dest)
    print(f"V7B_COMPOSITE floor={floor} global={payload['global']} -> {out}",
          flush=True)
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
