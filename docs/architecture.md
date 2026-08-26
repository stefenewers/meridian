# Architecture

Meridian is a fictional product. Every number it produces is simulated output from
synthetic demand. Nothing here is derived from any real ride-hail operator.

## What the system is for

An operations team wants to change something fleet-wide — a dispatch policy, a charging
constraint, the service area — and needs to know what it will cost before it ships. The
honest answer is usually "it depends on the night." Meridian's job is to make that
dependency legible: run the change against many sampled nights, report the spread, and
say plainly whether the evidence supports a launch, a pilot, or neither.

## System diagram

```
                        experiments/*.yaml
                     (versioned, code-reviewed)
                                 │
                                 ▼
┌──────────────────┐    ┌─────────────────────┐    ┌───────────────────────┐
│  apps/web        │    │ services/simulation │    │ data/models           │
│  Next.js + TS    │───▶│ FastAPI             │───▶│ demand_model.pkl      │
│                  │    │                     │    │ (LightGBM quantile)   │
│  · library       │◀───│  /experiments       │◀───│ + metrics.json        │
│  · workspace     │    │  /experiments/:id   │    └───────────────────────┘
│  · results       │    │  /validate          │              ▲
└──────────────────┘    │  /runs              │              │
         ▲              └──────────┬──────────┘     scripts/train_demand_model.py
         │                         │                (generates synthetic history,
   packages/shared                 │                 fits P10/P50/P90, reports
   (TypeScript types               ▼                 holdout pinball + coverage)
    mirroring pydantic)  ┌─────────────────────┐
                         │ runner.execute()    │
                         │  per replication:   │
                         │   sample_scenario   │──── quantile spread → arrivals
                         │   FleetSim (SimPy)  │──── vehicles, chargers, riders
                         │     └ dispatch      │──── greedy | OR-Tools assignment
                         │   summarise         │
                         │  aggregate → bands  │
                         │  recommend → verdict│
                         └─────────────────────┘
```

## Data flow

1. **Config in.** An `ExperimentConfig` arrives either from `experiments/*.yaml` or as an
   edited object posted from the workspace. Pydantic validates it. The config is hashed
   into an `input_snapshot`; nothing outside the config can influence a result.

2. **Forecast.** The trained model emits a P10/P50/P90 grid for every zone and
   15-minute interval, given day-of-week, weather, and event flags. Quantiles are sorted
   after prediction because independently fitted regressors can cross at low counts.

3. **Scenario draw.** `sample_scenario` turns the forecast into one night's arrivals.
   The draw is centred on the requested percentile and its spread comes from the model's
   own P10–P90 band, so zones with genuinely uncertain forecasts move more than tight
   ones. This is the step that carries forecast uncertainty into the decision.

4. **Simulate.** `FleetSim` runs the night. Both arms of a replication receive the
   **same** draw, which makes the comparison paired: differences are policy, not weather.

5. **Aggregate.** Replications collapse into intervals (mean, P10, P50, P90) per metric.
   No metric is ever reported as a bare point estimate.

6. **Recommend.** A rule over the experiment's own targets produces one of three
   verdicts with findings and guardrails attached.

## Simulation lifecycle

Time is minutes. Three SimPy processes run concurrently:

| Process | Cadence | Responsibility |
|---|---|---|
| `_arrivals_proc` | continuous | Injects each request at its own arrival time, spread uniformly inside its 15-minute interval |
| `_dispatch_proc` | every 1 min | Expires impatient riders, sends flat batteries to charge, matches pending requests to idle vehicles |
| `_reposition_proc` | every 15 min | Moves surplus idle vehicles toward forecast deficit two intervals ahead |

Vehicles are not processes themselves; each assignment spawns a short-lived process that
drives to pickup, carries the trip, and returns the vehicle to `idle`. Chargers are a
`simpy.Resource` whose capacity is the experiment's charger count, so queueing emerges
from contention rather than being assumed.

**Why dispatch ticks faster than the forecast.** The demand forecast is 15-minute;
matching is near-continuous. Ticking the matcher on the forecast interval batched every
rider in a quarter hour into a single instant and made wait times meaningless.

**Why repositioning looks two intervals ahead.** Crossing this metro takes longer than
one interval. Aiming at the next interval dispatched vehicles that arrived *after* the
demand they were sent for, which made the policy look worse than useless.

## Product decisions and tradeoffs

**Rule-based recommendation, not a learned one.** An operator has to be able to read why
a change was called, disagree with a threshold, change it in the config, and re-run. The
disagreement is almost always about the target, not the arithmetic. A model here would
add opacity and remove the argument.

**The verdict is three-valued, and "pilot" is the interesting one.** A binary
launch/reject is too crude. A change that moves the primary metric a long way without
quite reaching its goal is a pilot candidate: the goal may be wrong, or the gap may be
closable with capacity rather than policy. What earns a rejection is a change that does
not meaningfully move the metric it was designed to move.

**Greedy versus optimisation is a question, not an assumption.** `nearest_available` is
what most fleets start with. `demand_aware` batches pending requests and solves a
min-cost assignment with OR-Tools, encoding airport priority and battery reserve as cost
rather than hard rules. Whether the optimisation earns its complexity is exactly what the
product exists to test, so both are first-class and run head to head.

**Configs are files, not database rows.** An experiment definition moves through pull
request review like the code it tests. That is also what makes `config_version` and the
input snapshot meaningful.

**Runs are synchronous and in-process.** Correct for a prototype whose point is the
decision, not the job queue. It is also the first thing that would have to change.

**Paired replications over more replications.** Running both arms on identical demand
draws removes most of the variance from the comparison, which buys more signal per second
of compute than simply running more independent nights.

## Reproducibility

A run is reproducible from `(config, seed)` alone. Seeds derive deterministically from
the root seed and the replication index. Model training is a separate, explicit step so a
run can never silently retrain against a different artifact; the model version is part of
every run's provenance.

The subtle failure here was set iteration. `served` was a `set[str]`, and CPython
randomises string hashing per process, so iterating it fed a different order into the
destination gravity draw on every run — identical configs with identical seeds diverged
between processes while passing every in-process test. Sets are fine for membership and
unsafe to iterate anywhere the order can reach a sampled outcome.
`tests/test_reproducibility.py` shells out under two `PYTHONHASHSEED` values, because
that is the only way to catch it.

## What productionising this would take

Roughly in order of what would hurt first:

1. **Real demand.** Swap generated history for a trip feed, and retrain on a schedule.
   Everything downstream already treats the model as a versioned artifact, so this is a
   substitution rather than a rewrite. Model monitoring for drift becomes mandatory.
2. **A job queue.** Runs move to a worker pool with persisted status, so a 200-replication
   sweep is not an HTTP request. Run output goes to object storage keyed by run id.
3. **Routing.** Replace the circuity multiplier with a real routing engine and
   time-of-day speeds. This is the single biggest source of error in absolute pickup times.
4. **Calibration against observed operations.** Backtest a known past change and check
   the simulation's predicted direction and magnitude. Until this exists, Meridian is
   directionally useful and quantitatively unvalidated, and it should say so.
5. **Charging fidelity.** Charge curves rather than a linear rate, per-stall power
   limits, and depot-level electrical constraints. The flagship experiment is already
   charging-bound, so this is where the answer is most sensitive.
6. **Multi-tenancy and access control.** Experiment ownership, approvals for
   decision-ready status, and an audit trail of who ran what and what shipped.
7. **Statistical rigour.** Confidence intervals on the *difference* between arms, power
   analysis to size replication counts, and sequential stopping so long sweeps end when
   the answer is already clear.
