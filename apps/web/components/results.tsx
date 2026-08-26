'use client'

import { useState } from 'react'
import Link from 'next/link'
import type { Interval, RunOutput, Verdict } from '@meridian/shared'
import ZoneMap from '@/components/zone-map'
import UncertaintyChart from '@/components/uncertainty-chart'
import { DataRow, Panel, SectionLabel, SimulatedNotice } from '@/components/primitives'
import { DAY_NAMES, count, deltaPct, minutes, money, pct, windowLabel } from '@/lib/format'

const VERDICT_STYLE: Record<Verdict, { bar: string; text: string; ring: string }> = {
  launch: { bar: 'bg-signal-go', text: 'text-signal-go', ring: 'border-signal-go/30' },
  pilot: { bar: 'bg-signal-hold', text: 'text-signal-hold', ring: 'border-signal-hold/35' },
  do_not_launch: { bar: 'bg-signal-stop', text: 'text-signal-stop', ring: 'border-signal-stop/35' },
}

type Row = {
  key: string
  label: string
  fmt: (v: number) => string
  /** Which direction is an improvement, for colouring the delta. */
  better: 'lower' | 'higher'
  note?: string
}

const ROWS: Row[] = [
  { key: 'airport_p90_pickup_minutes', label: 'Airport P90 pickup', fmt: (v) => minutes(v), better: 'lower', note: 'Curbside at the terminal' },
  { key: 'median_pickup_minutes', label: 'Median pickup, fleet-wide', fmt: (v) => minutes(v), better: 'lower' },
  { key: 'p90_pickup_minutes', label: 'P90 pickup, fleet-wide', fmt: (v) => minutes(v), better: 'lower' },
  { key: 'completion_rate', label: 'Trip completion rate', fmt: (v) => pct(v), better: 'higher' },
  { key: 'completed_trips', label: 'Completed trips', fmt: count, better: 'higher' },
  { key: 'vehicle_utilization', label: 'Vehicle utilisation', fmt: (v) => pct(v), better: 'higher' },
  { key: 'deadhead_ratio', label: 'Deadhead share of miles', fmt: (v) => pct(v), better: 'lower' },
  { key: 'p90_charge_queue_minutes', label: 'P90 charger queue', fmt: (v) => minutes(v), better: 'lower' },
  { key: 'constrained_vehicle_hours', label: 'Vehicle-hours waiting to charge', fmt: (v) => v.toFixed(1), better: 'lower' },
  { key: 'cost_per_completed_trip', label: 'Cost per completed trip', fmt: money, better: 'lower', note: 'Illustrative unit economics' },
]

function Band({ i, fmt }: { i: Interval; fmt: (v: number) => string }) {
  return (
    <span className="font-mono text-3xs text-meta nums whitespace-nowrap">
      {fmt(i.p10)} – {fmt(i.p90)}
    </span>
  )
}

export default function Results({ run }: { run: RunOutput }) {
  const [arm, setArm] = useState<'baseline' | 'proposed'>('proposed')
  const rec = run.recommendation
  const style = VERDICT_STYLE[rec.verdict]
  const cfg = run.config
  const p = run.provenance

  return (
    <div className="space-y-10">
      {/* Decision */}
      <Panel className={`overflow-hidden border ${style.ring}`}>
        <div className={`h-1 ${style.bar}`} aria-hidden="true" />
        <div className="p-5 md:p-7">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4">
            <p className={`font-display font-extrabold text-xl tracking-tight ${style.text}`}>
              {rec.label}
            </p>
            <span className="font-mono text-2xs text-meta nums">
              {p.replications} replications per arm
            </span>
          </div>
          <p className="text-base md:text-[17px] text-ink leading-relaxed max-w-prose mb-6">
            {rec.summary}
          </p>

          <SectionLabel>What moved</SectionLabel>
          <ul className="grid md:grid-cols-2 gap-x-8 gap-y-3.5">
            {rec.findings.map((f, i) => (
              <li key={i} className="flex gap-2.5">
                <span
                  aria-hidden="true"
                  className={`shrink-0 mt-1.5 w-1.5 h-1.5 rounded-full ${
                    f.kind === 'win' ? 'bg-signal-go' : f.kind === 'risk' ? 'bg-signal-stop' : 'bg-meta/50'
                  }`}
                />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink leading-snug">
                    {f.headline}
                    <span className="sr-only"> ({f.kind === 'win' ? 'improvement' : f.kind === 'risk' ? 'risk' : 'neutral'})</span>
                  </p>
                  <p className="text-xs text-muted leading-relaxed mt-1">{f.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </Panel>

      {/* Metric comparison */}
      <section aria-labelledby="metrics-heading">
        <SectionLabel id="metrics-heading">Baseline versus proposed</SectionLabel>
        <Panel className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse">
            <caption className="sr-only">
              Simulated metric comparison. Each cell shows the mean across replications with the
              P10 to P90 band beneath it.
            </caption>
            <thead>
              <tr className="border-b rule">
                <th scope="col" className="text-left font-mono text-3xs uppercase tracking-[0.14em] text-meta font-normal px-4 py-2.5">Metric</th>
                <th scope="col" className="text-right font-mono text-3xs uppercase tracking-[0.14em] text-meta font-normal px-4 py-2.5">{cfg.baseline.label}</th>
                <th scope="col" className="text-right font-mono text-3xs uppercase tracking-[0.14em] text-meta font-normal px-4 py-2.5">{cfg.proposed.label}</th>
                <th scope="col" className="text-right font-mono text-3xs uppercase tracking-[0.14em] text-meta font-normal px-4 py-2.5">Change</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => {
                const b = run.baseline[row.key]
                const pr = run.proposed[row.key]
                if (!b || !pr) return null
                const improved = row.better === 'lower' ? pr.mean < b.mean : pr.mean > b.mean
                const flat = Math.abs(pr.mean - b.mean) < 1e-9
                return (
                  <tr key={row.key} className="border-b rule last:border-b-0 align-top">
                    <th scope="row" className="text-left px-4 py-3 font-normal">
                      <span className="text-sm text-ink">{row.label}</span>
                      {row.note && <span className="block font-mono text-3xs text-meta mt-0.5">{row.note}</span>}
                    </th>
                    <td className="text-right px-4 py-3">
                      <span className="font-mono text-sm text-ink nums block">{row.fmt(b.mean)}</span>
                      <Band i={b} fmt={row.fmt} />
                    </td>
                    <td className="text-right px-4 py-3">
                      <span className="font-mono text-sm text-ink nums block">{row.fmt(pr.mean)}</span>
                      <Band i={pr} fmt={row.fmt} />
                    </td>
                    <td className="text-right px-4 py-3">
                      <span
                        className={`font-mono text-sm nums ${
                          flat ? 'text-meta' : improved ? 'text-signal-go' : 'text-signal-stop'
                        }`}
                      >
                        {deltaPct(b.mean, pr.mean)}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Panel>
        <p className="mt-2.5 font-mono text-3xs text-meta">
          Large figure is the mean across replications. Smaller figure is the P10–P90 band.
        </p>
      </section>

      {/* Uncertainty */}
      <section aria-labelledby="uncertainty-heading">
        <SectionLabel id="uncertainty-heading">Confidence across replications</SectionLabel>
        <div className="grid lg:grid-cols-2 gap-6">
          <Panel className="p-4">
            <UncertaintyChart
              run={run} metric="airport_p90_pickup_minutes"
              target={cfg.targets.p90_pickup_minutes}
              label="Airport P90 pickup" unit="min"
            />
          </Panel>
          <Panel className="p-4">
            <UncertaintyChart
              run={run} metric="p90_charge_queue_minutes"
              target={cfg.targets.max_charger_queue_minutes}
              label="P90 charger queue" unit="min"
            />
          </Panel>
        </div>
        <p className="mt-2.5 text-xs text-muted leading-relaxed max-w-prose">
          Each pair is one night drawn from the demand model&apos;s spread. Bars past the dashed
          line miss the target on that night. A change that clears its goal on average and misses
          it on a busy night is a pilot, not a rollout.
        </p>
      </section>

      {/* Zone outcomes */}
      <section aria-labelledby="zones-heading">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <SectionLabel id="zones-heading">Zone-level service</SectionLabel>
          <div className="flex gap-1.5" role="radiogroup" aria-label="Which arm to show on the schematic">
            {(['baseline', 'proposed'] as const).map((a) => (
              <button
                key={a}
                role="radio"
                aria-checked={arm === a}
                onClick={() => setArm(a)}
                className={`font-mono text-2xs px-3 py-1 rounded-full border transition-colors ${
                  arm === a ? 'border-grove bg-grove/10 text-grove' : 'rule text-meta hover:border-line-strong'
                }`}
              >
                {a === 'baseline' ? cfg.baseline.label : cfg.proposed.label}
              </button>
            ))}
          </div>
        </div>
        <div className="grid lg:grid-cols-[1.25fr_1fr] gap-6 items-start">
          <ZoneMap run={run} arm={arm} />
          <Panel className="overflow-hidden">
            <table className="w-full border-collapse">
              <caption className="sr-only">Zone-level completion and mean pickup for the selected arm.</caption>
              <thead>
                <tr className="border-b rule">
                  <th scope="col" className="text-left font-mono text-3xs uppercase tracking-[0.14em] text-meta font-normal px-3 py-2">Zone</th>
                  <th scope="col" className="text-right font-mono text-3xs uppercase tracking-[0.14em] text-meta font-normal px-3 py-2">Requests</th>
                  <th scope="col" className="text-right font-mono text-3xs uppercase tracking-[0.14em] text-meta font-normal px-3 py-2">Completed</th>
                  <th scope="col" className="text-right font-mono text-3xs uppercase tracking-[0.14em] text-meta font-normal px-3 py-2">Mean pickup</th>
                </tr>
              </thead>
              <tbody>
                {run.zones.map((z) => {
                  const s = (arm === 'baseline' ? run.baseline_zones : run.proposed_zones)[z.id]
                  if (!s) return null
                  return (
                    <tr key={z.id} className="border-b rule last:border-b-0">
                      <th scope="row" className="text-left px-3 py-2 font-normal">
                        <span className="text-xs text-ink">{z.name}</span>
                        <span className="block font-mono text-3xs text-meta">
                          {z.id}{z.tier !== 'core' ? ` · ${z.tier}` : ''}
                        </span>
                      </th>
                      <td className="text-right px-3 py-2 font-mono text-xs nums text-muted">{count(s.requested)}</td>
                      <td className="text-right px-3 py-2 font-mono text-xs nums text-ink">{pct(s.completion_rate, 0)}</td>
                      <td className="text-right px-3 py-2 font-mono text-xs nums text-muted">{s.mean_pickup_minutes.toFixed(1)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </Panel>
        </div>
      </section>

      {/* Guardrails + provenance */}
      <section aria-labelledby="guardrails-heading" className="grid lg:grid-cols-2 gap-6">
        <div>
          <SectionLabel id="guardrails-heading">Launch guardrails</SectionLabel>
          <Panel className="p-4">
            <ul className="space-y-2.5">
              {rec.guardrails.map((g, i) => (
                <li key={i} className="flex gap-2.5 text-xs text-muted leading-relaxed">
                  <span aria-hidden="true" className="text-grove shrink-0">–</span>
                  {g}
                </li>
              ))}
            </ul>
          </Panel>
        </div>
        <div>
          <SectionLabel>Reproducibility</SectionLabel>
          <Panel className="p-4">
            <dl>
              <DataRow label="Run id" value={run.run_id} />
              <DataRow label="Input snapshot" value={p.input_snapshot} />
              <DataRow label="Seed" value={p.seed} />
              <DataRow label="Replications" value={p.replications} />
              <DataRow label="Config version" value={`v${p.config_version}`} />
              <DataRow label="Policy version" value={p.policy_version} />
              <DataRow label="Demand model" value={p.demand_model_version} />
              <DataRow label="Sim engine" value={p.sim_engine_version} />
              <DataRow
                label="Model P10–P90 coverage"
                value={p.demand_model_metrics.coverage_p10_p90 !== undefined
                  ? pct(p.demand_model_metrics.coverage_p10_p90, 1)
                  : '—'}
              />
              <DataRow
                label="Window"
                value={`${DAY_NAMES[cfg.demand.day_of_week]} ${windowLabel(cfg.run.window_start_hour, cfg.run.horizon_minutes)}`}
              />
              <DataRow label="Demand centre" value={cfg.demand.percentile.toUpperCase()} />
            </dl>
            <p className="mt-3 text-2xs text-meta leading-relaxed">
              Re-running this experiment with the same snapshot and seed reproduces these numbers
              exactly, including across machines.
            </p>
          </Panel>
        </div>
      </section>

      {/* Assumptions */}
      <section aria-labelledby="assumptions-heading">
        <SectionLabel id="assumptions-heading">Assumptions behind these numbers</SectionLabel>
        <Panel className="p-5">
          <div className="grid md:grid-cols-2 gap-x-10 gap-y-4 text-xs text-muted leading-relaxed">
            <p>
              <strong className="text-ink font-medium">Demand is synthetic.</strong> A LightGBM
              quantile model is trained on generated history, not observed trips. Its P10–P90 band
              covers {p.demand_model_metrics.coverage_p10_p90 !== undefined
                ? pct(p.demand_model_metrics.coverage_p10_p90, 1) : 'n/a'} of held-out nights
              against a nominal 80%.
            </p>
            <p>
              <strong className="text-ink font-medium">Travel is approximated.</strong> Distances
              are straight-line with a circuity multiplier; speed is a single average for the
              window. Absolute times are indicative, and the arm-to-arm comparison is the result.
            </p>
            <p>
              <strong className="text-ink font-medium">Unit economics are illustrative.</strong>{' '}
              Cost per trip uses assumed vehicle-hour, per-mile, and charging figures. Treat the
              direction as meaningful and the level as arbitrary.
            </p>
            <p>
              <strong className="text-ink font-medium">Autonomy is out of scope.</strong> No
              perception, planning, or remote assistance is modelled. Meridian tests fleet
              operations, not the driving stack.
            </p>
          </div>
          <SimulatedNotice className="mt-5 pt-4 border-t rule" />
        </Panel>
      </section>

      <div className="flex flex-wrap gap-3 pt-2">
        <Link
          href={`/experiments/${cfg.id}`}
          className="inline-flex items-center gap-2 border rule px-4 py-2 rounded-full font-mono text-2xs hover:border-line-strong transition-colors"
        >
          ← Back to workspace
        </Link>
      </div>
    </div>
  )
}
