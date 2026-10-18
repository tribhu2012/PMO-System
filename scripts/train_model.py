"""Retrain the project-delay model from the project_history table.

Usage:  python scripts/train_model.py
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

from projectpulse import config, ml
from projectpulse.database import get_engine, read_all


def main() -> None:
    history = read_all(get_engine())["project_history"]
    model = ml.train(history)
    ml.save(model)
    print(f"Best model: {model.model_name}")
    for name, score in sorted(model.cv_scores.items(), key=lambda kv: -kv[1]):
        print(f"  CV ROC AUC  {name:<20} {score:.3f}")
    for k, v in model.metrics.items():
        print(f"  test {k:<10} {v:.3f}")
    print(model.importance[["label", "importance"]].to_string(index=False))
    print(f"Saved -> {config.MODEL_PATH}")


if __name__ == "__main__":
    main()
