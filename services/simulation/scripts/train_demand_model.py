#!/usr/bin/env python3
"""Generate synthetic history, fit the quantile demand models, and save the artifact.

Run this once before the first experiment:

    python scripts/train_demand_model.py

It prints holdout metrics. The one to watch is coverage_p10_p90: if the P10-P90 band does
not contain roughly 80% of held-out observations, the uncertainty the product shows is
not trustworthy and scenario sampling inherits the problem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian.demand import generate_history, train_quantile_models  # noqa: E402
from meridian.model_store import save_model  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Train Meridian's quantile demand model.")
    ap.add_argument("--days", type=int, default=120, help="Nights of synthetic history to generate.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--save-history", action="store_true", help="Also write the generated history to data/.")
    args = ap.parse_args()

    print(f"Generating {args.days} nights of synthetic demand history (seed={args.seed})...")
    history = generate_history(days=args.days, seed=args.seed)
    print(f"  {len(history):,} zone-interval observations")

    if args.save_history:
        out = Path(__file__).resolve().parents[3] / "data" / "demand_history.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        history.to_csv(out, index=False)
        print(f"  history written to {out}")

    print("Fitting LightGBM quantile regressors at P10 / P50 / P90...")
    model = train_quantile_models(history, seed=args.seed)
    path = save_model(model)

    print("\nHoldout metrics (split by night, not at random):")
    for k, v in model.metrics.items():
        print(f"  {k:<20} {v}")
    cov = model.metrics["coverage_p10_p90"]
    verdict = "within tolerance" if 0.70 <= cov <= 0.90 else "OUT OF TOLERANCE"
    print(f"\n  P10-P90 coverage {cov:.1%} ({verdict}; nominal 80%)")
    print(f"\nSaved {model.version} -> {path}")

    metrics_path = path.parent / "demand_model_metrics.json"
    metrics_path.write_text(json.dumps({"version": model.version, **model.metrics}, indent=2))
    print(f"Metrics -> {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
