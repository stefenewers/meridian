#!/usr/bin/env python3
"""Run an experiment from the command line and print the decision.

    python scripts/run_experiment.py late-night-airport-expansion
    python scripts/run_experiment.py late-night-airport-expansion --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian.library import list_experiments, load_by_id  # noqa: E402
from meridian.runner import execute  # noqa: E402

METRICS = [
    ("airport_p90_pickup_minutes", "Airport P90 pickup (min)", 2),
    ("p90_pickup_minutes", "Fleet P90 pickup (min)", 2),
    ("median_pickup_minutes", "Median pickup (min)", 2),
    ("completion_rate", "Completion rate", 4),
    ("completed_trips", "Completed trips", 0),
    ("vehicle_utilization", "Vehicle utilisation", 4),
    ("deadhead_ratio", "Deadhead share", 4),
    ("p90_charge_queue_minutes", "P90 charger queue (min)", 2),
    ("constrained_vehicle_hours", "Vehicle-hours waiting to charge", 2),
    ("cost_per_completed_trip", "Cost per completed trip ($)", 3),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment_id", nargs="?", help="Experiment id, or omit to list them.")
    ap.add_argument("--json", type=Path, help="Write the full run payload here.")
    ap.add_argument("--replications", type=int, help="Override replication count.")
    args = ap.parse_args()

    if not args.experiment_id:
        print("Available experiments:")
        for cfg in list_experiments():
            print(f"  {cfg.id:<34} {cfg.title}")
        return 0

    cfg = load_by_id(args.experiment_id)
    if args.replications:
        cfg.run.replications = args.replications

    print(f"\n{cfg.title}")
    print(f"{cfg.question.strip()}\n")
    print(f"Running {cfg.run.replications} paired replications per arm (seed {cfg.run.seed})...")
    out = execute(cfg)

    print(f"\nRun {out.run_id}   snapshot {out.provenance['input_snapshot']}")
    print(f"{'Metric':<34}{'Baseline':>13}{'Proposed':>13}{'Delta':>11}")
    print("-" * 71)
    for key, label, dp in METRICS:
        b = out.baseline[key].mean
        p = out.proposed[key].mean
        d = p - b
        print(f"{label:<34}{b:>13.{dp}f}{p:>13.{dp}f}{d:>+11.{dp}f}")

    rec = out.recommendation
    print(f"\n=== {rec.label.upper()} ===")
    print(rec.summary)
    print("\nFindings:")
    for f in rec.findings:
        mark = {"win": "+", "risk": "!", "neutral": "="}[f.kind]
        print(f"  [{mark}] {f.headline}")
    print("\nGuardrails:")
    for g in rec.guardrails:
        print(f"  - {g}")

    if args.json:
        args.json.write_text(json.dumps(out.to_dict(), indent=2))
        print(f"\nFull payload -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
