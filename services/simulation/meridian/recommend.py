"""From metrics to a decision, with the reasoning left visible.

The verdict is a rule over the experiment's own targets, not a model. That is deliberate:
an operator has to be able to read why a change was called, disagree with a threshold,
change it in the config, and re-run. A learned recommender would be less useful here
because the disagreement is usually about the target, not the arithmetic.

Three verdicts:
  launch      - proposed clears every target, including in the upper tail
  pilot       - proposed wins on the primary outcome but a guardrail moves the wrong way
  do_not_launch - proposed misses the primary target, or regresses something important
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import ExperimentConfig
from .metrics import Interval

Verdict = str  # "launch" | "pilot" | "do_not_launch"

VERDICT_LABEL = {
    "launch": "Recommended",
    "pilot": "Pilot recommended",
    "do_not_launch": "Do not launch",
}


@dataclass
class Finding:
    kind: str          # "win" | "risk" | "neutral"
    metric: str
    headline: str
    detail: str


@dataclass
class Recommendation:
    verdict: Verdict
    label: str
    summary: str
    findings: list[Finding] = field(default_factory=list)
    guardrails: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "label": self.label,
            "summary": self.summary,
            "findings": [f.__dict__ for f in self.findings],
            "guardrails": self.guardrails,
        }


# A proposed arm that moves the primary metric by at least this much is worth piloting
# even if it does not reach the target outright.
MATERIAL_IMPROVEMENT_PCT = 5.0


def _delta_pct(base: float, prop: float) -> float:
    if base == 0:
        return 0.0
    return (prop - base) / abs(base) * 100.0


def build(
    cfg: ExperimentConfig,
    baseline: dict[str, Interval],
    proposed: dict[str, Interval],
) -> Recommendation:
    t = cfg.targets
    findings: list[Finding] = []
    guardrails: list[str] = []

    b_air_p90 = baseline["airport_p90_pickup_minutes"].mean
    p_air_p90 = proposed["airport_p90_pickup_minutes"].mean
    p_air_p90_tail = proposed["airport_p90_pickup_minutes"].p90

    b_comp = baseline["completion_rate"].mean
    p_comp = proposed["completion_rate"].mean

    b_qp90 = baseline["p90_charge_queue_minutes"].mean
    p_qp90 = proposed["p90_charge_queue_minutes"].mean
    p_q_tail = proposed["p90_charge_queue_minutes"].p90

    b_cost = baseline["cost_per_completed_trip"].mean
    p_cost = proposed["cost_per_completed_trip"].mean

    b_dead = baseline["deadhead_ratio"].mean
    p_dead = proposed["deadhead_ratio"].mean

    # --- primary outcome: the airport pickup target -------------------------------
    hits_target_mean = p_air_p90 <= t.p90_pickup_minutes
    hits_target_tail = p_air_p90_tail <= t.p90_pickup_minutes
    # Improvement is measured as a reduction, so a positive number is good news.
    air_improvement_pct = -_delta_pct(b_air_p90, p_air_p90)
    improves_materially = air_improvement_pct >= MATERIAL_IMPROVEMENT_PCT
    if hits_target_mean:
        findings.append(Finding(
            "win", "airport_p90_pickup_minutes",
            f"Airport P90 pickup falls to {p_air_p90:.1f} min, inside the {t.p90_pickup_minutes:.0f}-minute target",
            f"Baseline sits at {b_air_p90:.1f} min. Across replications the proposed arm's own upper tail "
            f"reaches {p_air_p90_tail:.1f} min, so the target holds on a typical night but "
            f"{'still holds' if hits_target_tail else 'is not guaranteed'} on a hot one.",
        ))
    else:
        kind = "win" if improves_materially else "risk"
        findings.append(Finding(
            kind, "airport_p90_pickup_minutes",
            f"Airport P90 pickup improves {air_improvement_pct:.0f}% to {p_air_p90:.1f} min, short of the "
            f"{t.p90_pickup_minutes:.0f}-minute target",
            f"Baseline is {b_air_p90:.1f} min. The change moves the metric substantially but does not close the "
            "gap on its own, which points at curbside capacity rather than dispatch logic as the remaining "
            "constraint." if improves_materially else
            f"Baseline is {b_air_p90:.1f} min. The change does not move the metric enough to justify the "
            "operational cost of running it.",
        ))

    # --- trip completion ----------------------------------------------------------
    comp_delta = (p_comp - b_comp) * 100
    if comp_delta >= -t.max_completion_loss_pct:
        findings.append(Finding(
            "win" if comp_delta > 0.2 else "neutral", "completion_rate",
            f"Trip completion {'rises' if comp_delta > 0 else 'holds'} at {p_comp * 100:.1f}%",
            f"Baseline completes {b_comp * 100:.1f}% of requests. Expansion adds demand as well as coverage, "
            "so completion holding is itself a result.",
        ))
    else:
        findings.append(Finding(
            "risk", "completion_rate",
            f"Trip completion drops {abs(comp_delta):.1f} points to {p_comp * 100:.1f}%",
            f"Baseline completes {b_comp * 100:.1f}%. The proposed arm is turning away more riders than it gains.",
        ))

    # --- the charging guardrail ---------------------------------------------------
    queue_over = p_q_tail > t.max_charger_queue_minutes
    if queue_over:
        findings.append(Finding(
            "risk", "p90_charge_queue_minutes",
            f"Charger queue reaches {p_q_tail:.0f} min in the upper tail, past the {t.max_charger_queue_minutes:.0f}-minute guardrail",
            f"On a median night the queue is {p_qp90:.1f} min against a baseline of {b_qp90:.1f} min. The risk is "
            "concentrated in high-demand draws, when more vehicles finish the window needing charge at once.",
        ))
        guardrails.append(
            f"Hold rollout if observed P90 charger queue exceeds {t.max_charger_queue_minutes:.0f} minutes on any pilot night."
        )
    else:
        findings.append(Finding(
            "neutral", "p90_charge_queue_minutes",
            f"Charger queue stays within guardrail at {p_q_tail:.0f} min in the tail",
            f"Median night is {p_qp90:.1f} min against a baseline of {b_qp90:.1f} min.",
        ))

    # --- cost and deadhead --------------------------------------------------------
    cost_delta = _delta_pct(b_cost, p_cost)
    findings.append(Finding(
        "risk" if cost_delta > 4 else "neutral", "cost_per_completed_trip",
        f"Cost per completed trip moves {cost_delta:+.1f}% to ${p_cost:.2f}",
        f"Baseline is ${b_cost:.2f}. Deadhead share moves from {b_dead * 100:.1f}% to {p_dead * 100:.1f}%, "
        "which is where most of the difference comes from.",
    ))

    # --- verdict ------------------------------------------------------------------
    if (not hits_target_mean and not improves_materially) or comp_delta < -t.max_completion_loss_pct:
        verdict = "do_not_launch"
        summary = (
            f"The proposed arm does not clear the primary target. Airport P90 pickup lands at "
            f"{p_air_p90:.1f} minutes against a {t.p90_pickup_minutes:.0f}-minute goal, and the change does not pay "
            "for its added cost. Re-scope before running this again."
        )
    elif queue_over or not hits_target_tail or not hits_target_mean:
        verdict = "pilot"
        reached = (
            f"clears the {t.p90_pickup_minutes:.0f}-minute target on a typical night"
            if hits_target_mean
            else f"closes {air_improvement_pct:.0f}% of the gap to the {t.p90_pickup_minutes:.0f}-minute target "
                 "without reaching it"
        )
        summary = (
            f"Airport P90 pickup improves from {b_air_p90:.1f} to {p_air_p90:.1f} minutes, which {reached}, and "
            f"trip completion holds at {p_comp * 100:.1f}%. It is not safe fleet-wide yet: "
            f"under upper-tail demand the charger queue reaches {p_q_tail:.0f} minutes against a "
            f"{t.max_charger_queue_minutes:.0f}-minute guardrail, and the constraint is charging capacity rather than "
            "dispatch. Run a staged pilot on the airport zone and two expansion zones, with charger headroom "
            "monitored nightly, before committing the full service area."
        )
        guardrails.append("Stage expansion zones one at a time, holding at least two weeks between additions.")
        guardrails.append("Add depot charger capacity before extending the pilot to the full service area.")
    else:
        verdict = "launch"
        summary = (
            f"The proposed arm clears every target, including in the upper tail. Airport P90 pickup improves from "
            f"{b_air_p90:.1f} to {p_air_p90:.1f} minutes with completion at {p_comp * 100:.1f}% and charging inside "
            "its guardrail."
        )

    guardrails.append("Every figure here is simulated output from synthetic demand, not observed performance.")
    return Recommendation(verdict=verdict, label=VERDICT_LABEL[verdict], summary=summary,
                          findings=findings, guardrails=guardrails)
