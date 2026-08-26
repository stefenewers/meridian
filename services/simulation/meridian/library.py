"""Loading the versioned experiment library off disk.

Configs live in `experiments/*.yaml` at the repo root, not in a database. They are
reviewable in a pull request, which is the point: an experiment's definition should move
through the same process as the code it tests.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import ExperimentConfig

EXPERIMENTS_DIR = Path(__file__).resolve().parents[3] / "experiments"

# Editorial metadata for the scenario library view. Kept beside the loader rather than in
# the YAML so the config files stay purely about what the simulation does.
STATUS: dict[str, dict[str, str]] = {
    "late-night-airport-expansion": {"status": "decision_ready", "owner": "ops-strategy"},
    "rainy-friday-surge": {"status": "running", "owner": "ops-strategy"},
    "depot-charger-outage": {"status": "draft", "owner": "fleet-reliability"},
    "new-service-zone-launch": {"status": "draft", "owner": "market-expansion"},
}


def load_config(path: Path) -> ExperimentConfig:
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    return ExperimentConfig.model_validate(raw)


def load_by_id(experiment_id: str) -> ExperimentConfig:
    path = EXPERIMENTS_DIR / f"{experiment_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No experiment config at {path}")
    return load_config(path)


def list_experiments() -> list[ExperimentConfig]:
    return [load_config(p) for p in sorted(EXPERIMENTS_DIR.glob("*.yaml"))]


def raw_yaml(experiment_id: str) -> str:
    return (EXPERIMENTS_DIR / f"{experiment_id}.yaml").read_text()
