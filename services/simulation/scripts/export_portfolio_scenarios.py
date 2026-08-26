#!/usr/bin/env python3
"""Export a precomputed scenario matrix for the portfolio's interactive explorer.

The portfolio cannot run SimPy, so it reads results this script produced. Everything
here goes through Meridian's real code path: `runner.execute` runs the simulation,
`metrics.aggregate` builds the bands, and `recommend.build` produces the verdict. This
file adds no simulation and no recommendation logic of its own. It selects
configurations, runs them, and reshapes the output for a browser.

    python scripts/export_portfolio_scenarios.py
    python scripts/export_portfolio_scenarios.py --portfolio ../../www.stefenewers.com

Determinism: scenario values depend only on code, config, model artifact, and seed.
Re-running produces identical metrics. Only `generatedAt` changes, which
`--check-determinism` ignores when comparing against an existing artifact.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian.config import ExperimentConfig  # noqa: E402
from meridian.library import load_by_id  # noqa: E402
from meridian.model_store import ModelNotTrained, load_model  # noqa: E402
from meridian.runner import execute  # noqa: E402

SCHEMA_VERSION = 1
EXPERIMENT_ID = "late-night-airport-expansion"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO_ROOT / "data" / "portfolio" / "scenarios.json"
PORTFOLIO_RELATIVE = Path("public") / "meridian" / "scenarios.json"

# ── the control matrix ───────────────────────────────────────────────────────
# Three dimensions the simulator genuinely supports, each of which changes the
# decision for a different reason. Deliberately small: every extra dimension
# multiplies runtime and buys a visitor nothing after the first few seconds.

CHARGER_OPTIONS = [24, 36, 48]

# `percentile` lives on DemandConfig, which is shared by both arms. That is what keeps
# the design paired: changing the demand condition changes the night both arms face,
# never one of them. Labels describe what the quantile means operationally.
DEMAND_OPTIONS = [
    {"value": "p10", "label": "Light", "note": "A quiet night, low end of the forecast"},
    {"value": "p50", "label": "Typical", "note": "Centred on the median forecast"},
    {"value": "p90", "label": "Upper-tail", "note": "A busy night, top of the forecast"},
]

DISPATCH_OPTIONS = [
    {"value": "nearest_available", "label": "Nearest available",
     "note": "Greedy matching, oldest request first"},
    {"value": "demand_aware", "label": "Demand-aware",
     "note": "Batched min-cost assignment solved with OR-Tools"},
]

# What the explorer shows, and how each metric should be read.
METRIC_SPEC: list[dict[str, Any]] = [
    {"key": "airport_p90_pickup_minutes", "label": "Airport pickup, P90",
     "unit": "min", "better": "lower", "decimals": 1, "primary": True,
     "target": "p90_pickup_minutes", "targetKind": "target",
     "note": "Curbside at the terminal"},
    {"key": "completion_rate", "label": "Trip completion", "unit": "%",
     "better": "higher", "decimals": 1, "scale": 100, "primary": True},
    {"key": "p90_charge_queue_minutes", "label": "Charger queue, P90",
     "unit": "min", "better": "lower", "decimals": 1, "primary": True,
     "target": "max_charger_queue_minutes", "targetKind": "guardrail"},
    {"key": "cost_per_completed_trip", "label": "Cost per completed trip",
     "unit": "$", "better": "lower", "decimals": 2, "primary": True},
    {"key": "completed_trips", "label": "Completed trips", "unit": "",
     "better": "higher", "decimals": 0, "primary": False},
    {"key": "deadhead_ratio", "label": "Deadhead share of miles", "unit": "%",
     "better": "lower", "decimals": 1, "scale": 100, "primary": False},
]


def scenario_id(chargers: int, demand: str, dispatch: str) -> str:
    return f"chargers-{chargers}_demand-{demand}_dispatch-{dispatch.replace('_', '-')}"


def _finite(x: float, where: str) -> float:
    if not math.isfinite(x):
        raise ValueError(f"non-finite value at {where}: {x!r}")
    return x


def _interval(raw: dict[str, float], spec: dict[str, Any], where: str) -> dict[str, float]:
    """Normalise one metric's band, applying the display scale once, here."""
    scale = spec.get("scale", 1)
    out = {k: round(_finite(raw[k], f"{where}.{k}") * scale, 4) for k in ("mean", "p10", "p50", "p90")}
    # Aggregation sorts nothing, so assert rather than assume the band is ordered.
    if not (out["p10"] <= out["p50"] <= out["p90"]):
        raise ValueError(f"band out of order at {where}: {out}")
    return out


def build_scenario(
    cfg: ExperimentConfig, chargers: int, demand: str, dispatch: str, model
) -> dict[str, Any]:
    """Run one proposed-arm configuration through the real simulation."""
    run_cfg = cfg.model_copy(deep=True)
    # Only the proposed arm's fleet and policy move. The baseline is never touched, which
    # is the whole point of the module: a visitor changes one side of the comparison.
    run_cfg.proposed.fleet.chargers = chargers
    run_cfg.proposed.policy.dispatch = dispatch  # type: ignore[assignment]
    run_cfg.demand.percentile = demand  # type: ignore[assignment]

    out = execute(run_cfg, model=model).to_dict()
    targets = run_cfg.targets.model_dump()

    metrics: list[dict[str, Any]] = []
    for spec in METRIC_SPEC:
        key = spec["key"]
        b = _interval(out["baseline"][key], spec, f"{key}.baseline")
        p = _interval(out["proposed"][key], spec, f"{key}.proposed")
        entry: dict[str, Any] = {
            "key": key,
            "label": spec["label"],
            "unit": spec["unit"],
            "better": spec["better"],
            "decimals": spec["decimals"],
            "primary": spec["primary"],
            "baseline": b,
            "proposed": p,
            "delta": round(p["mean"] - b["mean"], 4),
        }
        if spec.get("note"):
            entry["note"] = spec["note"]
        if spec.get("target"):
            entry["threshold"] = {
                "value": round(float(targets[spec["target"]]), 4),
                "kind": spec["targetKind"],
            }
        metrics.append(entry)

    return {
        "id": scenario_id(chargers, demand, dispatch),
        "selection": {"chargers": chargers, "demand": demand, "dispatch": dispatch},
        "configuration": {
            "baseline": {
                "label": run_cfg.baseline.label,
                "vehicles": run_cfg.baseline.fleet.vehicles,
                "chargers": run_cfg.baseline.fleet.chargers,
                "dispatch": run_cfg.baseline.policy.dispatch,
                "airportPriority": run_cfg.baseline.policy.airport_priority,
                "serviceAreaExpansion": run_cfg.baseline.policy.service_area_expansion,
            },
            "proposed": {
                "label": run_cfg.proposed.label,
                "vehicles": run_cfg.proposed.fleet.vehicles,
                "chargers": run_cfg.proposed.fleet.chargers,
                "dispatch": run_cfg.proposed.policy.dispatch,
                "airportPriority": run_cfg.proposed.policy.airport_priority,
                "airportBatteryReserve": run_cfg.proposed.policy.airport_battery_reserve,
                "repositioning": run_cfg.proposed.policy.demand_aware_repositioning,
                "serviceAreaExpansion": run_cfg.proposed.policy.service_area_expansion,
            },
        },
        "metrics": metrics,
        "recommendation": out["recommendation"],
        "bindingConstraint": binding_constraint(metrics),
        "provenance": {
            "inputSnapshot": out["provenance"]["input_snapshot"],
            "seed": out["provenance"]["seed"],
            "replications": out["provenance"]["replications"],
        },
    }


def binding_constraint(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Which threshold the proposed arm strains hardest.

    Presentation only. This does not grade the experiment or influence the verdict,
    which `recommend.build` has already produced. It ranks the metrics that carry a
    threshold by how far the proposed arm's upper tail sits past it, so the explorer can
    name the constraint instead of leaving a visitor to infer it from four numbers.
    """
    worst: dict[str, Any] | None = None
    for m in metrics:
        t = m.get("threshold")
        if not t:
            continue
        # Thresholds here are all "must stay at or below".
        tail = m["proposed"]["p90"]
        breach = (tail - t["value"]) / t["value"] if t["value"] else 0.0
        if worst is None or breach > worst["breach"]:
            worst = {"key": m["key"], "label": m["label"], "breach": round(breach, 4),
                     "kind": t["kind"], "threshold": t["value"], "tail": tail}
    if worst is None:
        return {"key": None, "label": "None measured", "breached": False}
    return {
        "key": worst["key"],
        "label": worst["label"],
        "breached": worst["breach"] > 0,
        "kind": worst["kind"],
        "threshold": worst["threshold"],
        "proposedTail": worst["tail"],
        "basis": "Largest upper-tail exceedance of a configured threshold across scenarios.",
    }


def export(model) -> dict[str, Any]:
    cfg = load_by_id(EXPERIMENT_ID)
    total = len(CHARGER_OPTIONS) * len(DEMAND_OPTIONS) * len(DISPATCH_OPTIONS)
    scenarios: list[dict[str, Any]] = []
    i = 0
    for chargers in CHARGER_OPTIONS:
        for demand in DEMAND_OPTIONS:
            for dispatch in DISPATCH_OPTIONS:
                i += 1
                t0 = time.time()
                s = build_scenario(cfg, chargers, demand["value"], dispatch["value"], model)
                scenarios.append(s)
                print(f"  [{i:>2}/{total}] {s['id']:<58} "
                      f"{s['recommendation']['label']:<18} {time.time() - t0:5.1f}s", flush=True)

    probe = execute(cfg.model_copy(deep=True), model=model).to_dict()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "experiment": {
            "id": cfg.id,
            "name": cfg.title,
            "question": cfg.question.strip(),
            "seed": cfg.run.seed,
            "replications": cfg.run.replications,
            "engineVersion": probe["provenance"]["sim_engine_version"],
            "modelVersion": probe["provenance"]["demand_model_version"],
            "policyVersion": probe["provenance"]["policy_version"],
            "configVersion": cfg.config_version,
            "demandModelCoverageP10P90": probe["provenance"]["demand_model_metrics"].get("coverage_p10_p90"),
            "syntheticDemand": True,
            "pairedReplications": True,
            "disclaimer": probe["provenance"]["disclaimer"],
        },
        "controls": {
            "chargers": CHARGER_OPTIONS,
            "demand": DEMAND_OPTIONS,
            "dispatch": DISPATCH_OPTIONS,
        },
        # The configuration the case study documents, so the explorer opens on it.
        "defaultSelection": {
            "chargers": cfg.proposed.fleet.chargers,
            "demand": cfg.demand.percentile,
            "dispatch": cfg.proposed.policy.dispatch,
        },
        "scenarios": scenarios,
    }


def validate(doc: dict[str, Any]) -> list[str]:
    """Fail loudly rather than shipping a subtly broken artifact."""
    errors: list[str] = []
    expected = {
        scenario_id(c, d["value"], p["value"])
        for c in CHARGER_OPTIONS for d in DEMAND_OPTIONS for p in DISPATCH_OPTIONS
    }
    got = [s["id"] for s in doc["scenarios"]]
    if len(got) != len(set(got)):
        errors.append("duplicate scenario ids")
    missing = expected - set(got)
    if missing:
        errors.append(f"missing combinations: {sorted(missing)}")
    extra = set(got) - expected
    if extra:
        errors.append(f"unexpected combinations: {sorted(extra)}")

    seeds = {s["provenance"]["seed"] for s in doc["scenarios"]}
    reps = {s["provenance"]["replications"] for s in doc["scenarios"]}
    if len(seeds) != 1:
        errors.append(f"scenarios used more than one seed: {seeds}")
    if len(reps) != 1:
        errors.append(f"scenarios used more than one replication count: {reps}")

    verdicts = {"launch", "pilot", "do_not_launch"}
    for s in doc["scenarios"]:
        where = s["id"]
        rec = s["recommendation"]
        if rec["verdict"] not in verdicts:
            errors.append(f"{where}: verdict {rec['verdict']!r} is not one Meridian produces")
        if not rec.get("summary") or not rec.get("guardrails"):
            errors.append(f"{where}: recommendation is missing summary or guardrails")
        keys = {m["key"] for m in s["metrics"]}
        for spec in METRIC_SPEC:
            if spec["key"] not in keys:
                errors.append(f"{where}: missing metric {spec['key']}")
        for m in s["metrics"]:
            for arm in ("baseline", "proposed"):
                band = m[arm]
                for k, v in band.items():
                    if not math.isfinite(v):
                        errors.append(f"{where}.{m['key']}.{arm}.{k} is not finite")
                if not (band["p10"] <= band["p50"] <= band["p90"]):
                    errors.append(f"{where}.{m['key']}.{arm}: p10<=p50<=p90 violated")

    default = doc["defaultSelection"]
    if scenario_id(default["chargers"], default["demand"], default["dispatch"]) not in set(got):
        errors.append("defaultSelection has no matching scenario")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Where to write the artifact.")
    ap.add_argument("--portfolio", type=Path,
                    help="Portfolio repo root; also writes public/meridian/scenarios.json there.")
    ap.add_argument("--check-determinism", type=Path,
                    help="Compare scenario values against an existing artifact and exit non-zero on drift.")
    args = ap.parse_args()

    try:
        model = load_model()
    except ModelNotTrained as exc:
        print(exc)
        return 1

    total = len(CHARGER_OPTIONS) * len(DEMAND_OPTIONS) * len(DISPATCH_OPTIONS)
    print(f"Exporting {total} scenarios from {EXPERIMENT_ID} "
          f"(seed {load_by_id(EXPERIMENT_ID).run.seed}, real simulation, paired arms)...")
    doc = export(model)

    errors = validate(doc)
    if errors:
        print("\nVALIDATION FAILED")
        for e in errors:
            print(f"  - {e}")
        return 2
    print(f"\nValidation passed: {len(doc['scenarios'])} scenarios, unique ids, ordered bands, "
          f"single seed {doc['experiment']['seed']}, {doc['experiment']['replications']} paired replications.")

    if args.check_determinism:
        prior = json.loads(args.check_determinism.read_text())
        a = json.dumps(prior.get("scenarios"), sort_keys=True)
        b = json.dumps(doc["scenarios"], sort_keys=True)
        if a != b:
            print(f"DETERMINISM CHECK FAILED: scenario values differ from {args.check_determinism}")
            return 3
        print(f"Determinism check passed: scenario values identical to {args.check_determinism}")

    payload = json.dumps(doc, indent=2, sort_keys=False) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(payload)
    size_kb = len(payload.encode()) / 1024
    print(f"Wrote {args.out}  ({size_kb:.1f} KB)")

    if args.portfolio:
        dest = args.portfolio.expanduser().resolve() / PORTFOLIO_RELATIVE
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.out, dest)
        print(f"Copied  {dest}")

    if size_kb > 250:
        print(f"WARNING: artifact is {size_kb:.0f} KB, above the 250 KB budget for the portfolio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
