"""Database access: engine creation, schema build, bulk load and table reads."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache

import pandas as pd
from sqlalchemy import Engine, create_engine, inspect, text

from . import config
from .models import TABLE_LOAD_ORDER, Base, DataImport

log = logging.getLogger(__name__)

DATE_COLUMNS = {
    "employees": ["hire_date"],
    "projects": ["start_date", "planned_end_date", "actual_end_date"],
    "sprints": ["start_date", "end_date"],
    "tasks": ["created_date", "started_date", "due_date", "completion_date"],
    "risks": ["identified_date", "resolved_date"],
    "scrum_ceremonies": ["ceremony_date"],
}
NUMERIC_COLUMNS = {
    "projects": ["budget", "actual_cost"],
    "tasks": ["planned_hours", "actual_hours"],
    "scrum_ceremonies": ["attendance_rate"],
    "performance": ["peer_review_score"],
}
NULLABLE_INT_COLUMNS = {"tasks": ["sprint_id", "employee_id"], "scrum_ceremonies": ["sprint_id"]}


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    url = url or config.DATABASE_URL
    if url.startswith("postgres://"):  # Heroku/Render style URLs
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True, future=True)


def is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"


def create_schema(engine: Engine, conn=None) -> None:
    """Drop and recreate all data tables (the ``data_imports`` log is kept).

    PostgreSQL runs the canonical DDL in ``sql/01_schema.sql``; other engines
    (the SQLite demo fallback) use the equivalent ORM metadata.
    """
    if is_postgres(engine):
        _run_sql_file(engine, "01_schema.sql", conn)
    else:
        data_tables = [Base.metadata.tables[n] for n in TABLE_LOAD_ORDER]
        Base.metadata.drop_all(conn or engine, tables=data_tables)
        Base.metadata.create_all(conn or engine)


def create_views(engine: Engine, conn=None) -> None:
    if is_postgres(engine):
        _run_sql_file(engine, "02_views.sql", conn)


def _run_sql_file(engine: Engine, name: str, conn=None) -> None:
    """Execute a multi-statement SQL script verbatim (no parameter parsing, so '%' is safe)."""
    sql = (config.SQL_DIR / name).read_text()
    if conn is not None:
        conn.connection.driver_connection.execute(sql)
        return
    with engine.begin() as c:
        c.connection.driver_connection.execute(sql)


def load_tables(engine: Engine, tables: dict[str, pd.DataFrame], conn=None) -> dict[str, int]:
    """Bulk insert DataFrames in foreign-key order. Returns row counts."""
    if conn is None:
        with engine.begin() as c:
            return load_tables(engine, tables, c)
    counts = {}
    for name in TABLE_LOAD_ORDER:
        df = tables[name].copy()
        for col in DATE_COLUMNS.get(name, []):
            df[col] = pd.to_datetime(df[col]).dt.date
        df = df.astype(object).where(df.notna(), None)
        df.to_sql(name, conn, if_exists="append", index=False, chunksize=2000,
                  method="multi")
        counts[name] = len(df)
        log.info("loaded %-17s %6d rows", name, len(df))
    return counts


def replace_all(engine: Engine, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Rebuild the schema and load ``tables`` in ONE transaction.

    If anything fails (a constraint, a lost connection) the whole import is rolled
    back and the previous data is untouched.
    """
    with engine.begin() as conn:
        create_schema(engine, conn)
        counts = load_tables(engine, tables, conn)
        create_views(engine, conn)
    return counts


def record_import(engine: Engine, source: str, counts: dict[str, int], files: list[str] | None = None,
                  data_as_of=None) -> None:
    DataImport.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(DataImport.__table__.insert().values(
            imported_at=datetime.now().replace(microsecond=0), source=source,
            files=", ".join(files) if files else None, row_counts=json.dumps(counts),
            data_as_of=pd.Timestamp(data_as_of).date() if data_as_of is not None else None))


def import_history(engine: Engine, limit: int = 20) -> pd.DataFrame:
    """Most recent loads first. Empty if nothing has been logged yet."""
    if "data_imports" not in inspect(engine).get_table_names():
        return pd.DataFrame(columns=["import_id", "imported_at", "source", "files", "row_counts",
                                     "data_as_of"])
    with engine.connect() as conn:
        return pd.read_sql(text(f"SELECT * FROM data_imports ORDER BY imported_at DESC, import_id DESC "
                                f"LIMIT {int(limit)}"), conn)


def database_ready(engine: Engine) -> bool:
    try:
        names = set(inspect(engine).get_table_names())
    except Exception:  # pragma: no cover - connection problems
        return False
    if not set(TABLE_LOAD_ORDER) <= names:
        return False
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT COUNT(*) FROM tasks")).scalar())


def prepare(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Normalise dtypes (dates -> datetime64, decimals -> float, nullable ints)."""
    out = {}
    for name, df in tables.items():
        df = df.copy()
        for col in DATE_COLUMNS.get(name, []):
            df[col] = pd.to_datetime(df[col])
        for col in NUMERIC_COLUMNS.get(name, []):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
        for col in NULLABLE_INT_COLUMNS.get(name, []):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        out[name] = df
    return out


def read_all(engine: Engine | None = None) -> dict[str, pd.DataFrame]:
    engine = engine or get_engine()
    with engine.connect() as conn:
        raw = {name: pd.read_sql_table(name, conn) for name in TABLE_LOAD_ORDER}
    return prepare(raw)
