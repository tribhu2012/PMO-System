"""Write the import workbooks.

Usage:
    python scripts/make_templates.py                  # blank templates -> templates/
    python scripts/make_templates.py --sample         # also filled sample workbooks -> data/sample/
    python scripts/make_templates.py --from-database  # export the current database -> data/export/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401

from projectpulse import config, importer
from projectpulse.data_generator import generate_dataset
from projectpulse.database import get_engine, read_all


def _write(books: dict[str, bytes], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, data in books.items():
        (out / name).write_bytes(data)
        print(f"  {out / name}  ({len(data) / 1024:,.0f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", action="store_true", help="also write workbooks filled with demo data")
    parser.add_argument("--from-database", action="store_true", help="export the current database")
    args = parser.parse_args()

    print("Blank templates:")
    _write(importer.write_workbooks(), config.ROOT_DIR / "templates")
    if args.sample:
        print("Sample workbooks (synthetic data):")
        _write(importer.write_workbooks(generate_dataset()), config.ROOT_DIR / "data" / "sample")
    if args.from_database:
        print("Export of the current database:")
        _write(importer.write_workbooks(read_all(get_engine())), config.ROOT_DIR / "data" / "export")


if __name__ == "__main__":
    main()
