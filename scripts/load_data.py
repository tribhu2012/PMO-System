"""Create the schema, generate synthetic data, load it and train the delay model.

Usage:
    python scripts/load_data.py                       # uses DATABASE_URL
    python scripts/load_data.py --database-url postgresql://user:pw@localhost:5432/projectpulse
    python scripts/load_data.py --skip-model
    python scripts/load_data.py --if-empty       # only when there is no data yet (Docker start-up)
"""
from __future__ import annotations

import argparse
import logging
import time

import _bootstrap  # noqa: F401

from projectpulse import config, ml
from projectpulse.data_generator import generate_dataset
from projectpulse.database import database_ready, get_engine, read_all, record_import, replace_all


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database-url", default=config.DATABASE_URL)
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    parser.add_argument("--as-of", default=config.DATA_AS_OF)
    parser.add_argument("--skip-model", action="store_true", help="do not train the ML model")
    parser.add_argument("--if-empty", action="store_true",
                        help="do nothing if the database already has data (keeps imported spreadsheets)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    engine = get_engine(args.database_url)
    print(f"Target database: {engine.url.render_as_string(hide_password=True)} ({engine.dialect.name})")
    if args.if_empty and database_ready(engine):
        print("Database already has data; nothing to do (--if-empty).")
        return

    t0 = time.perf_counter()
    tables = generate_dataset(seed=args.seed, as_of=args.as_of)
    print(f"Generated data in {time.perf_counter() - t0:.1f}s")

    counts = replace_all(engine, tables)
    record_import(engine, "synthetic", counts, data_as_of=args.as_of)
    print("Loaded: " + ", ".join(f"{k}={v:,}" for k, v in counts.items()))

    if not args.skip_model:
        model = ml.train(read_all(engine)["project_history"])
        ml.save(model)
        m = model.metrics
        print(f"Trained {model.model_name}: ROC AUC {m['roc_auc']:.3f}, accuracy {m['accuracy']:.3f} "
              f"-> {config.MODEL_PATH}")
    print(f"Done in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
