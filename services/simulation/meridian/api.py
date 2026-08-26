"""FastAPI surface. Thin on purpose: it validates, delegates, and serialises.

Runs are executed synchronously and cached in-process. That is the right amount of
infrastructure for a prototype whose point is the decision, not the job queue;
`docs/architecture.md` describes what productionising this would actually take.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from . import __version__
from .config import ExperimentConfig
from .library import STATUS, list_experiments, load_by_id, raw_yaml
from .model_store import ModelNotTrained, model_available
from .runner import execute
from .world import DEPOTS, ZONES

app = FastAPI(
    title="Meridian Simulation Service",
    version=__version__,
    description=(
        "Pre-production experimentation for autonomous ride-hail fleet operations. "
        "Meridian is a fictional product; all outputs are simulated from synthetic demand."
    ),
)

# The UI is a separate origin in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_RUN_CACHE: dict[str, dict[str, Any]] = {}
_RUNS_BY_EXPERIMENT: dict[str, list[str]] = {}


class RunRequest(BaseModel):
    """Either run a stored experiment by id, or post an edited config to run ad hoc."""
    experiment_id: str | None = None
    config: dict | None = None


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "demand_model_trained": model_available(),
        "notice": "Fictional product. Simulated output only.",
    }


@app.get("/world")
def world() -> dict:
    return {
        "zones": [
            {"id": z.id, "name": z.name, "x": z.x, "y": z.y, "tier": str(z.tier),
             "peak_intensity": z.peak_intensity}
            for z in ZONES
        ],
        "depots": [
            {"id": d.id, "name": d.name, "x": d.x, "y": d.y, "chargers": d.chargers}
            for d in DEPOTS
        ],
    }


@app.get("/experiments")
def experiments() -> list[dict]:
    out = []
    for cfg in list_experiments():
        meta = STATUS.get(cfg.id, {"status": "draft", "owner": cfg.owner})
        out.append({
            "id": cfg.id,
            "title": cfg.title,
            "question": cfg.question,
            "owner": meta["owner"],
            "status": meta["status"],
            "config_version": cfg.config_version,
            "replications": cfg.run.replications,
            "run_count": len(_RUNS_BY_EXPERIMENT.get(cfg.id, [])),
            "latest_run_id": (_RUNS_BY_EXPERIMENT.get(cfg.id) or [None])[-1],
        })
    return out


@app.get("/experiments/{experiment_id}")
def experiment(experiment_id: str) -> dict:
    try:
        cfg = load_by_id(experiment_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    meta = STATUS.get(cfg.id, {"status": "draft", "owner": cfg.owner})
    return {
        "config": cfg.model_dump(mode="json"),
        "yaml": raw_yaml(experiment_id),
        "status": meta["status"],
        "owner": meta["owner"],
        "input_snapshot": cfg.input_snapshot_hash(),
        "runs": _RUNS_BY_EXPERIMENT.get(experiment_id, []),
    }


@app.post("/experiments/validate")
def validate(payload: dict) -> dict:
    """Schema feedback for the config editor. Returns field-level errors, never raises."""
    try:
        cfg = ExperimentConfig.model_validate(payload)
    except ValidationError as exc:
        return {
            "valid": False,
            "errors": [
                {"path": ".".join(str(p) for p in e["loc"]), "message": e["msg"], "type": e["type"]}
                for e in exc.errors()
            ],
        }
    return {"valid": True, "errors": [], "input_snapshot": cfg.input_snapshot_hash()}


@app.post("/runs")
def create_run(req: RunRequest) -> dict:
    if req.config is not None:
        try:
            cfg = ExperimentConfig.model_validate(req.config)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
    elif req.experiment_id:
        try:
            cfg = load_by_id(req.experiment_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=400, detail="Provide experiment_id or config")

    try:
        out = execute(cfg).to_dict()
    except ModelNotTrained as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _RUN_CACHE[out["run_id"]] = out
    _RUNS_BY_EXPERIMENT.setdefault(cfg.id, []).append(out["run_id"])
    return out


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    if run_id not in _RUN_CACHE:
        raise HTTPException(status_code=404, detail=f"No run {run_id} in this process")
    return _RUN_CACHE[run_id]
