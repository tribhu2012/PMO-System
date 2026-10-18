"""Central configuration for ProjectPulse.

Values come from environment variables (optionally loaded from a ``.env`` file)
so the same code runs locally, in Docker and on Streamlit Community Cloud.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT_DIR / "sql"
MODEL_DIR = ROOT_DIR / "models"
MODEL_PATH = MODEL_DIR / "delay_model.joblib"

# PostgreSQL is the primary target. A SQLite file is used as a zero-setup
# fallback so the dashboard can be demoed without a database server.
DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{(ROOT_DIR / 'projectpulse.db').as_posix()}"
)

APP_NAME = "ProjectPulse"

# Reproducibility of the synthetic data set.
RANDOM_SEED = int(os.getenv("PP_SEED", "42"))

# The data set describes 24 months of history ending on this "as of" date.
DATA_AS_OF = os.getenv("PP_AS_OF", "2026-09-30")
HISTORY_MONTHS = 24

# ---------------------------------------------------------------------------
# Business rules (kept in one place so analysts can tune them)
# ---------------------------------------------------------------------------
HEALTH_WEIGHTS = {"schedule": 0.40, "budget": 0.30, "risk": 0.30}
HEALTH_GREEN = 80  # >= green
HEALTH_YELLOW = 60  # >= yellow, otherwise red

PERFORMANCE_WEIGHTS = {
    "task_completion": 0.30,
    "on_time": 0.30,
    "sprint_contribution": 0.20,
    "collaboration": 0.20,
}

OVERLOAD_THRESHOLD = 1.00  # utilisation above this is "overloaded"
UNDERUTILISED_THRESHOLD = 0.70  # utilisation below this is "under-utilised"
SPRINT_SUCCESS_THRESHOLD = 0.85  # commitment reliability for a "successful" sprint
HIGH_RISK_SCORE = 15  # probability x impact (1-25) at or above this is "high"

DELAY_CLASS_BANDS = {"Low Risk": 0.35, "Medium Risk": 0.65}  # upper bounds
