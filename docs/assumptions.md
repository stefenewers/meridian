# Assumptions and limitations

Meridian is a fictional product built to demonstrate product, data, and systems work. It
is **not** affiliated with, derived from, or representative of any real ride-hail
operator, and it uses no proprietary data. Every figure it produces is simulated output
from synthetic demand.

This document exists because a simulation that does not state its assumptions is not
decision support. It is a number generator.

## Why this does not simulate autonomous driving

Meridian models a **fleet operations** problem, not a **driving** problem. There is no
perception, no planning, no control, no remote assistance, and no safety-case modelling.

That is deliberate, for three reasons:

1. **It is the wrong altitude for the decision.** Whether to expand a service area or
   change a dispatch policy is answered by supply, demand, energy, and geometry. Vehicle
   autonomy is a constant across both arms of every experiment here, so modelling it in
   detail would add cost and change no answer.
2. **Credible perception and planning simulation is a different discipline** with
   different tooling, different validation, and orders of magnitude more compute. A
   shallow version would be worse than none, because it would invite conclusions it
   cannot support.
3. **Honesty about scope.** A portfolio project that claimed to simulate self-driving
   would be claiming something it does not do. This claims to simulate the operational
   envelope those vehicles run inside, which is a real and unglamorous problem.

Vehicles here are units of supply with a location, a battery, and a status.

## Demand

- **The history is generated, not observed.** `generate_history()` synthesises
  zone/interval request counts with structure a real feed would plausibly have: a
  within-window decay for core zones, a late arrival bank at the airport, weekend and
  weather multipliers, and an event surge on two zones. Counts come from a negative
  binomial so dispersion exceeds Poisson.
- **The model can only be as good as that structure.** Holdout metrics (pinball loss,
  P10–P90 coverage) are honest measurements *against synthetic data*. Coverage near 80%
  means the model has learned the generator, not that it would forecast a real city.
- **Quantiles are fitted independently** and sorted afterwards to enforce monotonicity.
  This is a pragmatic fix, not a principled joint quantile model.
- **Demand is exogenous.** Riders do not respond to price, to wait times, or to service
  quality. A real expansion would induce demand; this does not model that.

## Geography and travel

- **Meridian Bay is invented.** Zone coordinates are abstract miles on a flat grid.
- **Distance is straight-line times a circuity multiplier of 1.35.** There is no road
  network, no turn restrictions, and no congestion.
- **Speed is a single average** for the window (24 mph), with a flat multiplier in wet
  weather. Late night was chosen partly because that assumption is least wrong then.
- **An intra-zone pickup floor of 0.55 miles** stands in for the rider being somewhere
  inside a zone rather than at its centroid.
- **Consequence:** absolute pickup times are indicative only. The comparison between two
  arms under identical geography is the result; the level is not a forecast.

## Fleet and energy

- **Energy is linear in distance** at roughly a 240-mile usable range. No temperature
  effects, no HVAC load, no battery degradation.
- **Charging is linear** at a fixed rate to a fixed target state of charge. Real charge
  curves taper substantially; this will understate time at high states of charge.
- **Chargers are interchangeable** and share one pool across both depots. No per-stall
  power limits and no depot-level electrical constraint.
- **Vehicles never fail.** No breakdowns, no cleaning holds, no collisions, no
  interventions.
- **Starting state of charge is drawn from a wide normal.** The width matters: a tight
  distribution synchronises the whole fleet onto the charge trigger at the same moment and
  manufactures a queue that is an artifact of initialisation rather than of capacity.

## Riders

- **Patience is a hard 14-minute threshold.** Real abandonment is a gradual hazard that
  varies by rider, trip purpose, and alternative options.
- **Destinations follow a gravity model** over zone attraction and distance, with a fixed
  share of core demand heading to the airport. Nobody takes the same trip twice, and there
  are no round trips.
- **No rider chooses between operators**, and there is no price.

## Economics

- **Unit costs are illustrative.** Vehicle-hour, per-mile, and per-charge figures are
  assumed constants used only to compute cost per completed trip. Treat the *direction*
  of the change as meaningful and the *level* as arbitrary.
- **No revenue model.** Meridian reports cost per completed trip, not margin.

## Statistical limitations

- **Replications are paired**, which removes demand variance from the comparison but
  means the reported bands describe *outcome spread across nights*, not a confidence
  interval on the difference between arms.
- **No significance testing.** With 20 replications, a small difference between arms is
  not distinguishable from noise, and the product does not currently say so. This is the
  most important missing piece of statistical rigour.
- **Targets are inputs, not findings.** The verdict grades against thresholds someone
  chose. Changing `targets` in the config changes the verdict without changing a single
  simulated outcome, which is by design and worth remembering when reading one.

## What a result here does and does not mean

A Meridian result is **evidence for a decision under uncertainty**, at the resolution of
"is this direction worth a pilot, and what should we watch while we run it."

It is **not** a forecast, not a capacity plan, not a safety argument, and not a
substitute for a controlled rollout. The flagship experiment's recommendation is a staged
pilot precisely because the simulation cannot tell you what a real night will do — it can
only tell you which risk to instrument first.
