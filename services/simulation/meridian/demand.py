"""Probabilistic demand: synthetic history, a quantile model, and scenario sampling.

The chain is deliberately short and inspectable:

    generate_history()  ->  train_quantile_models()  ->  forecast_grid()  ->  sample_scenario()

The model predicts P10/P50/P90 requests per zone per 15-minute interval. Those quantiles
are not decoration: `sample_scenario` draws the actual arrival counts a simulation run
sees from the fitted spread, so demand uncertainty propagates all the way into the
recommendation. Choosing "P90" in the UI shifts the centre of that draw, which is how an
operator asks "what if the night runs hot".

The history is generated, not observed. See docs/assumptions.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .world import ZONES, ZONES_BY_ID, ZoneTier

INTERVAL_MINUTES = 15
MODEL_VERSION = "demand-lgbm-q-0.3.0"
QUANTILES = (0.1, 0.5, 0.9)
_FEATURES = [
    "zone_idx", "interval", "hour", "day_of_week", "is_weekend",
    "is_raining", "is_event", "peak_intensity", "is_airport",
]


def _shape(zone: "object", interval: int, hour: int) -> float:
    """Within-window demand curve, per zone type.

    Core zones decay through the night. The airport does the opposite: it peaks with the
    late arrival bank around 23:00-01:00, which is exactly why airport policy is worth an
    experiment.
    """
    if zone.tier is ZoneTier.AIRPORT:
        # Bump centred on the late arrival bank.
        return 0.28 + 1.15 * float(np.exp(-((interval - 11) ** 2) / 18.0))
    if zone.tier is ZoneTier.EXPANSION:
        return 0.30 + 0.45 * float(np.exp(-((interval - 5) ** 2) / 40.0))
    return 0.45 + 0.75 * float(np.exp(-((interval - 3) ** 2) / 45.0))


def generate_history(
    *, days: int = 120, seed: int = 7, window_start_hour: int = 21, horizon_minutes: int = 360
) -> pd.DataFrame:
    """Synthesise zone/interval request counts with the structure a real feed would have.

    Counts are drawn from a negative binomial so the spread is wider than Poisson, which
    is what makes P10/P90 separate enough to matter.
    """
    rng = np.random.default_rng(seed)
    intervals = horizon_minutes // INTERVAL_MINUTES
    rows = []
    for day in range(days):
        dow = day % 7
        is_weekend = int(dow >= 5)
        # Weather and events are exogenous and correlated with nothing else here.
        raining = int(rng.random() < 0.22)
        event = int(rng.random() < 0.14)
        for zi, zone in enumerate(ZONES):
            for interval in range(intervals):
                hour = (window_start_hour + (interval * INTERVAL_MINUTES) // 60) % 24
                mu = zone.peak_intensity * _shape(zone, interval, hour)
                mu *= 1.0 + 0.22 * is_weekend
                mu *= 1.0 + 0.30 * raining
                if event and zone.id in ("MB-05", "MB-02"):
                    # A stadium letting out spills into the neighbouring core zone.
                    mu *= 1.0 + 0.85 * float(np.exp(-((interval - 6) ** 2) / 12.0))
                mu = max(mu, 0.05)
                # NB(mean=mu, dispersion k): var = mu + mu^2/k
                k = 6.0
                p = k / (k + mu)
                count = int(rng.negative_binomial(k, p))
                rows.append(
                    {
                        "day": day, "zone_id": zone.id, "zone_idx": zi, "interval": interval,
                        "hour": hour, "day_of_week": dow, "is_weekend": is_weekend,
                        "is_raining": raining, "is_event": event,
                        "peak_intensity": zone.peak_intensity,
                        "is_airport": int(zone.tier is ZoneTier.AIRPORT),
                        "requests": count,
                    }
                )
    return pd.DataFrame(rows)


@dataclass
class DemandModel:
    """Three quantile regressors plus the metadata that makes a run auditable."""
    models: dict[float, object]
    version: str = MODEL_VERSION
    metrics: dict | None = None

    def predict_grid(self, *, day_of_week: int, is_raining: bool, is_event: bool,
                     window_start_hour: int, horizon_minutes: int) -> pd.DataFrame:
        intervals = horizon_minutes // INTERVAL_MINUTES
        rows = []
        for zi, zone in enumerate(ZONES):
            for interval in range(intervals):
                rows.append({
                    "zone_id": zone.id, "zone_idx": zi, "interval": interval,
                    "hour": (window_start_hour + (interval * INTERVAL_MINUTES) // 60) % 24,
                    "day_of_week": day_of_week, "is_weekend": int(day_of_week >= 5),
                    "is_raining": int(is_raining), "is_event": int(is_event),
                    "peak_intensity": zone.peak_intensity,
                    "is_airport": int(zone.tier is ZoneTier.AIRPORT),
                })
        grid = pd.DataFrame(rows)
        X = grid[_FEATURES]
        for q, model in self.models.items():
            grid[f"p{int(q * 100)}"] = np.clip(model.predict(X), 0.0, None)
        # Quantile regressors are fit independently and can cross at low counts.
        # Sorting restores monotonicity so P10 <= P50 <= P90 always holds.
        qcols = [f"p{int(q * 100)}" for q in sorted(self.models)]
        grid[qcols] = np.sort(grid[qcols].to_numpy(), axis=1)
        return grid


def _pinball_loss(y: np.ndarray, yhat: np.ndarray, q: float) -> float:
    d = y - yhat
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


def train_quantile_models(history: pd.DataFrame, *, seed: int = 7) -> DemandModel:
    """Fit one LightGBM quantile regressor per level, and report honest holdout metrics."""
    import lightgbm as lgb

    # Split by day, not at random: adjacent intervals within a day are correlated, and a
    # random split would leak that structure and flatter the model.
    cutoff = int(history["day"].max() * 0.8)
    train = history[history["day"] <= cutoff]
    test = history[history["day"] > cutoff]

    Xtr, ytr = train[_FEATURES], train["requests"]
    Xte, yte = test[_FEATURES], test["requests"]

    models: dict[float, object] = {}
    metrics: dict[str, float] = {}
    for q in QUANTILES:
        m = lgb.LGBMRegressor(
            objective="quantile", alpha=q, n_estimators=300, learning_rate=0.06,
            num_leaves=31, min_child_samples=30, random_state=seed, verbose=-1,
        )
        m.fit(Xtr, ytr, categorical_feature=["zone_idx"])
        pred = np.clip(m.predict(Xte), 0.0, None)
        models[q] = m
        metrics[f"pinball_p{int(q * 100)}"] = round(_pinball_loss(yte.to_numpy(), pred, q), 4)

    # Coverage is the number that actually matters for scenario generation: if the
    # P10-P90 band does not contain ~80% of held-out nights, the uncertainty bands the
    # product shows are lying.
    lo = np.clip(models[0.1].predict(Xte), 0.0, None)
    hi = np.clip(models[0.9].predict(Xte), 0.0, None)
    lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
    metrics["coverage_p10_p90"] = round(float(np.mean((yte >= lo) & (yte <= hi))), 4)
    metrics["mae_p50"] = round(float(np.mean(np.abs(yte - np.clip(models[0.5].predict(Xte), 0, None)))), 4)
    metrics["n_train"] = int(len(train))
    metrics["n_test"] = int(len(test))
    return DemandModel(models=models, metrics=metrics)


def sample_scenario(grid: pd.DataFrame, *, centre: str, seed: int, served: set[str]) -> dict[tuple[str, int], int]:
    """Draw one night's arrivals per (zone, interval) from the forecast spread.

    `centre` picks which quantile the draw is centred on. The spread is taken from the
    model's own P10-P90 band, so a night sampled at P90 is not just "P50 times a
    constant": zones whose forecasts are genuinely uncertain move more than zones whose
    forecasts are tight. That is the property that makes the charger-queue risk in the
    flagship experiment show up only in the upper tail.
    """
    rng = np.random.default_rng(seed)
    out: dict[tuple[str, int], int] = {}
    for row in grid.itertuples(index=False):
        if row.zone_id not in served:
            continue
        centre_val = float(getattr(row, centre))
        spread = max(float(row.p90) - float(row.p10), 0.6)
        # Lognormal-ish multiplicative noise keeps counts non-negative and right-skewed.
        sigma = min(spread / max(centre_val, 1.0), 1.1) * 0.42
        draw = centre_val * float(rng.lognormal(mean=-0.5 * sigma**2, sigma=sigma))
        out[(row.zone_id, int(row.interval))] = int(max(0, rng.poisson(max(draw, 0.01))))
    return out
