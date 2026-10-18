"""Generate the TechNova Solutions synthetic data set and write it to CSV.

Usage:
    python scripts/generate_data.py                 # -> data/*.csv
    python scripts/generate_data.py --out exports --seed 7
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import _bootstrap  # noqa: F401

from projectpulse import config
from projectpulse.data_generator import generate_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(config.ROOT_DIR / "data"), help="output directory")
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    parser.add_argument("--as-of", default=config.DATA_AS_OF, help="snapshot date (YYYY-MM-DD)")
    args = parser.parse_args()

    t0 = time.perf_counter()
    tables = generate_dataset(seed=args.seed, as_of=args.as_of)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"  {name:<17} {len(df):>6,} rows -> {out / (name + '.csv')}")
    print(f"Generated in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
