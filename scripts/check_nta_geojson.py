#!/usr/bin/env python3
"""R8 gate: validate web/public/data/nta.geojson against the checkpoint-1 counts."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "web" / "public" / "data" / "nta.geojson"
EXPECTED_FEATURES = 197  # residential NTA count reported at checkpoint 1
MAX_BYTES = 2 * 1024 * 1024
REQUIRED = [
    "nta2020", "ntaname", "boroname", "hvi_rank", "surface_temp", "greenspace",
    "pct_households_ac", "median_income", "mhlth", "depression", "trees_per_km2",
    "heat_group", "distress_group", "overlap_flag",
]
BANNED = ["pct_black_pop"]


def main() -> int:
    size = PATH.stat().st_size
    data = json.loads(PATH.read_text())
    feats = data["features"]
    errors = []
    if len(feats) != EXPECTED_FEATURES:
        errors.append(f"feature count {len(feats)} != {EXPECTED_FEATURES}")
    for f in feats:
        props = f["properties"]
        missing = [k for k in REQUIRED if k not in props]
        if missing:
            errors.append(f"{props.get('nta2020')}: missing {missing}")
        extra = [k for k in props if k.lower() in BANNED]
        if extra:
            errors.append(f"{props.get('nta2020')}: banned property {extra}")
    if size > MAX_BYTES:
        errors.append(f"size {size} > {MAX_BYTES}")
    print(f"features {len(feats)}, size {size} bytes")
    for e in errors[:20]:
        print("FAIL:", e)
    if errors:
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
