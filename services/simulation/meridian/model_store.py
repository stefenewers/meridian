"""Where the trained demand model lives, and how a run gets hold of it.

Training is a separate step on purpose. A run must not silently retrain: the model
version is part of a run's provenance, and a result you cannot tie to a specific model is
not reproducible. If the artifact is missing, the API says so rather than improvising.
"""

from __future__ import annotations

import pickle
from pathlib import Path

from .demand import DemandModel

ARTIFACT_DIR = Path(__file__).resolve().parents[3] / "data" / "models"
ARTIFACT_PATH = ARTIFACT_DIR / "demand_model.pkl"


class ModelNotTrained(RuntimeError):
    pass


def save_model(model: DemandModel) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    with ARTIFACT_PATH.open("wb") as fh:
        pickle.dump(model, fh)
    return ARTIFACT_PATH


def load_model() -> DemandModel:
    if not ARTIFACT_PATH.exists():
        raise ModelNotTrained(
            f"No demand model at {ARTIFACT_PATH}. Run: python scripts/train_demand_model.py"
        )
    with ARTIFACT_PATH.open("rb") as fh:
        return pickle.load(fh)


def model_available() -> bool:
    return ARTIFACT_PATH.exists()
