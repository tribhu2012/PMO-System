"""Project delay prediction.

Training data: ``project_history`` - mid-project snapshots of TechNova's archived
projects (2019-2024) with a known outcome (``delayed`` = finished after the
planned end date). Three candidate models are compared with stratified 5-fold
cross-validated ROC AUC; the winner is evaluated once on a held-out test set.

Scoring: the live portfolio's current metrics are mapped onto the same five
features and scored, giving each active project a delay probability and a
Low / Medium / High risk class.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import config
from .metrics import classify_delay

FEATURES = [
    "budget_utilization",
    "open_risks",
    "avg_resource_utilization",
    "sprint_velocity",
    "tasks_remaining",
]
FEATURE_LABELS = {
    "budget_utilization": "Budget Utilization (AC ÷ EV)",
    "open_risks": "Open Risks",
    "avg_resource_utilization": "Avg Resource Utilization",
    "sprint_velocity": "Sprint Velocity (SP)",
    "tasks_remaining": "Tasks Remaining",
}
TARGET = "delayed"


def _candidates(seed: int) -> dict[str, Pipeline]:
    return {
        "Logistic Regression": Pipeline([
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, C=1.0)),
        ]),
        "Random Forest": Pipeline([
            ("clf", RandomForestClassifier(n_estimators=300, max_depth=6, min_samples_leaf=5,
                                           random_state=seed, n_jobs=-1)),
        ]),
        "Gradient Boosting": Pipeline([
            ("clf", GradientBoostingClassifier(n_estimators=200, max_depth=2, learning_rate=0.05,
                                               subsample=0.8, random_state=seed)),
        ]),
    }


@dataclass
class DelayModel:
    pipeline: Pipeline
    model_name: str
    metrics: dict[str, float]
    cv_scores: dict[str, float]
    confusion: np.ndarray
    roc: pd.DataFrame
    importance: pd.DataFrame
    train_medians: pd.Series
    n_train: int
    n_test: int
    trained_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        # Features that cannot be measured yet (e.g. no closed sprint) fall back to typical values.
        return self.pipeline.predict_proba(X[FEATURES].astype(float).fillna(self.train_medians))[:, 1]

    def score_frame(self, X: pd.DataFrame) -> pd.DataFrame:
        out = X.copy()
        out["delay_probability"] = self.predict_proba(X)
        out["risk_class"] = out.delay_probability.map(classify_delay)
        return out

    def local_drivers(self, row: pd.Series) -> pd.DataFrame:
        """What-if attribution: change in probability when each feature is reset to
        the training median. Positive = this feature is pushing delay risk up."""
        x = row[FEATURES].astype(float).to_frame().T
        base = float(self.predict_proba(x)[0])
        out = []
        for f in FEATURES:
            alt = x.copy()
            alt[f] = self.train_medians[f]
            out.append({
                "feature": f,
                "label": FEATURE_LABELS[f],
                "value": float(x[f].iloc[0]),
                "typical": float(self.train_medians[f]),
                "impact": base - float(self.predict_proba(alt)[0]),
            })
        return pd.DataFrame(out).sort_values("impact", ascending=False)


def train(history: pd.DataFrame, seed: int = config.RANDOM_SEED) -> DelayModel:
    X, y = history[FEATURES].astype(float), history[TARGET].astype(int)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y,
                                              random_state=seed)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    cv_scores = {name: float(cross_val_score(est, X_tr, y_tr, cv=cv, scoring="roc_auc").mean())
                 for name, est in _candidates(seed).items()}
    best_name = max(cv_scores, key=cv_scores.get)
    model = clone(_candidates(seed)[best_name]).fit(X_tr, y_tr)

    proba = model.predict_proba(X_te)[:, 1]
    pred = (proba >= 0.5).astype(int)
    fpr, tpr, thr = roc_curve(y_te, proba)
    perm = permutation_importance(model, X_te, y_te, scoring="roc_auc", n_repeats=25,
                                  random_state=seed)
    importance = pd.DataFrame({
        "feature": FEATURES,
        "label": [FEATURE_LABELS[f] for f in FEATURES],
        "importance": perm.importances_mean,
        "std": perm.importances_std,
    }).sort_values("importance", ascending=False)

    return DelayModel(
        pipeline=model,
        model_name=best_name,
        metrics={
            "roc_auc": float(roc_auc_score(y_te, proba)),
            "accuracy": float(accuracy_score(y_te, pred)),
            "precision": float(precision_score(y_te, pred, zero_division=0)),
            "recall": float(recall_score(y_te, pred, zero_division=0)),
            "f1": float(f1_score(y_te, pred, zero_division=0)),
            "base_rate": float(y.mean()),
        },
        cv_scores=cv_scores,
        confusion=confusion_matrix(y_te, pred, labels=[0, 1]),
        roc=pd.DataFrame({"fpr": fpr, "tpr": tpr, "threshold": thr}),
        importance=importance,
        train_medians=X_tr.median(),
        n_train=len(X_tr),
        n_test=len(X_te),
    )


def save(model: DelayModel, path=config.MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load(path=config.MODEL_PATH) -> DelayModel | None:
    try:
        return joblib.load(path) if path.exists() else None
    except Exception:  # stale pickle from another library version
        return None


def current_features(project_metrics: pd.DataFrame) -> pd.DataFrame:
    """Map live project metrics onto the model's feature space."""
    pm = project_metrics
    out = pd.DataFrame({
        "project_id": pm.project_id,
        "project_name": pm.project_name,
        "budget_utilization": (pm.ac / pm.ev.replace(0, np.nan)).fillna(1.0),
        "open_risks": pm.open_risks,
        "avg_resource_utilization": pm.team_utilization.fillna(pm.team_utilization.median()),
        "sprint_velocity": pm.velocity_recent.fillna(pm.velocity_recent.median()),
        "tasks_remaining": pm.tasks_remaining,
    })
    return out.fillna(out.median(numeric_only=True))
