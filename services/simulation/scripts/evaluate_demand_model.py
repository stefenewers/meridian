#!/usr/bin/env python3
"""Evaluate the trained demand model and print a model card.

Separate from training on purpose: this is the artifact you read before trusting a run,
and it should be runnable against a model you did not just fit.

    python scripts/evaluate_demand_model.py

The number that governs whether Meridian's uncertainty bands mean anything is P10-P90
coverage. Pinball loss tells you the quantiles are fitted; coverage tells you the
interval is honest. A model with good pinball loss and 55% coverage would still make
every confidence band in the product a lie.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian.demand import _FEATURES, QUANTILES, generate_history  # noqa: E402
from meridian.model_store import ModelNotTrained, load_model  # noqa: E402
from meridian.world import ZONES_BY_ID  # noqa: E402


def main() -> int:
    try:
        model = load_model()
    except ModelNotTrained as exc:
        print(exc)
        return 1

    # Fresh nights the model has never seen, generated with a different seed.
    holdout = generate_history(days=40, seed=9109)
    X, y = holdout[_FEATURES], holdout["requests"].to_numpy()

    preds = {q: np.clip(model.models[q].predict(X), 0.0, None) for q in QUANTILES}
    lo, hi = np.minimum(preds[0.1], preds[0.9]), np.maximum(preds[0.1], preds[0.9])

    print(f"\nMODEL CARD — {model.version}")
    print("=" * 62)
    print("Task        Zone-level ride requests per 15-minute interval")
    print("Model       LightGBM, one quantile regressor per level (0.1 / 0.5 / 0.9)")
    print(f"Features    {', '.join(_FEATURES)}")
    print("Target      Request count (negative binomial in the generator)")
    print("Data        SYNTHETIC. Generated, not observed. See docs/assumptions.md.")

    print("\nTRAINING METRICS (reported at fit time)")
    for k, v in (model.metrics or {}).items():
        print(f"  {k:<22} {v}")

    print("\nFRESH-HOLDOUT EVALUATION (40 unseen nights, seed 9109)")
    for q in QUANTILES:
        d = y - preds[q]
        pinball = float(np.mean(np.maximum(q * d, (q - 1) * d)))
        below = float(np.mean(y <= preds[q]))
        print(f"  q={q:<4} pinball {pinball:6.4f}   empirical below {below:6.2%} (nominal {q:.0%})")

    coverage = float(np.mean((y >= lo) & (y <= hi)))
    width = float(np.mean(hi - lo))
    print(f"\n  P10-P90 coverage    {coverage:6.2%}  (nominal 80%)")
    print(f"  Mean interval width {width:6.2f} requests")
    print(f"  MAE at P50          {float(np.mean(np.abs(y - preds[0.5]))):6.3f}")

    print("\nCOVERAGE BY ZONE (where the interval is honest, and where it is not)")
    print(f"  {'zone':<26}{'tier':<11}{'coverage':>9}{'width':>8}")
    for zid, zone in ZONES_BY_ID.items():
        mask = (holdout["zone_id"] == zid).to_numpy()
        if not mask.any():
            continue
        cov = float(np.mean((y[mask] >= lo[mask]) & (y[mask] <= hi[mask])))
        w = float(np.mean(hi[mask] - lo[mask]))
        flag = "" if 0.68 <= cov <= 0.92 else "  <- outside tolerance"
        print(f"  {zone.name:<26}{str(zone.tier):<11}{cov:>8.1%}{w:>8.2f}{flag}")

    print("\nLIMITATIONS")
    print("  - Trained and evaluated on generated data. Metrics measure whether the model")
    print("    learned the generator, not whether it would forecast a real market.")
    print("  - Quantiles are fitted independently and sorted afterwards to enforce")
    print("    monotonicity, rather than fitted jointly.")
    print("  - Demand is exogenous: it does not respond to wait times, price, or supply.")
    print("  - No drift monitoring, because there is no live feed to drift from.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
