"""Validate spreadsheets and load them into the database (replaces all data).

Usage:
    python scripts/import_excel.py data/sample/*.xlsx              # validate, then load
    python scripts/import_excel.py exports/*.xlsx exports/*.csv --dry-run
    python scripts/import_excel.py ... --problems problems.csv     # write the full problem list

Exit code is 1 when validation finds errors (nothing is loaded).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import _bootstrap  # noqa: F401

from projectpulse import config, importer, metrics, ml
from projectpulse.database import database_ready, get_engine, prepare, read_all, record_import, replace_all


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path, help=".xlsx or .csv files")
    parser.add_argument("--database-url", default=config.DATABASE_URL)
    parser.add_argument("--dry-run", action="store_true", help="validate only, do not load")
    parser.add_argument("--problems", type=Path, help="write every problem found to this CSV")
    args = parser.parse_args()

    engine = get_engine(args.database_url)
    history = read_all(engine)["project_history"] if database_ready(engine) else None
    t0 = time.perf_counter()
    result = importer.validate_files([(f.name, f.read_bytes()) for f in args.files], history)
    print(f"Checked {len(args.files)} file(s) in {time.perf_counter() - t0:.1f}s: "
          f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)")
    problems = result.problem_frame()
    if len(problems):
        print(problems.head(25).to_string(index=False))
        if len(problems) > 25:
            print(f"... and {len(problems) - 25} more")
    if args.problems:
        problems.to_csv(args.problems, index=False)
        print(f"Problem list -> {args.problems}")
    if not result.ok:
        print("Nothing was loaded. Fix the errors above and run again.")
        return 1
    if args.dry_run:
        print("Dry run: the files are valid. Nothing was loaded.")
        return 0

    counts = replace_all(engine, result.tables)
    as_of = metrics.data_as_of(prepare(result.tables))
    record_import(engine, "spreadsheet", counts, [f.name for f in args.files], as_of)
    print("Loaded: " + ", ".join(f"{k}={v:,}" for k, v in counts.items()))
    model = ml.train(read_all(engine)["project_history"])
    ml.save(model)
    print(f"Retrained {model.model_name}: ROC AUC {model.metrics['roc_auc']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
