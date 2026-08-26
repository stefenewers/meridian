'use client'

import { useCallback, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { ExperimentConfig, ValidationResult } from '@meridian/shared'
import { api, ApiError, type ExperimentDetail } from '@/lib/api'
import { DataRow, Panel, SectionLabel, SimulatedNotice } from '@/components/primitives'
import { DAY_NAMES, windowLabel } from '@/lib/format'

type JobState =
  | { phase: 'idle' }
  | { phase: 'validating' }
  | { phase: 'running'; step: string }
  | { phase: 'error'; message: string }

/** Labelled numeric control. Native range + number so keyboard and screen readers work. */
function Control({
  label, help, value, min, max, step, unit, onChange, id,
}: {
  label: string; help: string; value: number; min: number; max: number
  step: number; unit?: string; id: string
  onChange: (v: number) => void
}) {
  return (
    <div className="py-3 border-b rule last:border-b-0">
      <div className="flex items-baseline justify-between gap-4 mb-1.5">
        <label htmlFor={id} className="text-sm font-medium text-ink">{label}</label>
        <output htmlFor={id} className="font-mono text-sm text-ink nums">
          {value}{unit ? ` ${unit}` : ''}
        </output>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-describedby={`${id}-help`}
        className="w-full accent-grove cursor-pointer"
      />
      <p id={`${id}-help`} className="text-2xs text-meta mt-1.5 leading-relaxed">{help}</p>
    </div>
  )
}

function Toggle({
  label, help, checked, onChange, id,
}: { label: string; help: string; checked: boolean; id: string; onChange: (v: boolean) => void }) {
  return (
    <div className="py-3 border-b rule last:border-b-0">
      <div className="flex items-start gap-3">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          aria-describedby={`${id}-help`}
          className="mt-0.5 w-4 h-4 accent-grove cursor-pointer shrink-0"
        />
        <div className="min-w-0">
          <label htmlFor={id} className="text-sm font-medium text-ink cursor-pointer">{label}</label>
          <p id={`${id}-help`} className="text-2xs text-meta mt-1 leading-relaxed">{help}</p>
        </div>
      </div>
    </div>
  )
}

function ArmSummary({ label, arm, tone }: { label: string; arm: ExperimentConfig['baseline']; tone: 'base' | 'prop' }) {
  const policy = arm.policy
  const on = (b: boolean) => (b ? 'On' : 'Off')
  return (
    <div className={`p-4 rounded-card border ${tone === 'prop' ? 'border-grove/30 bg-grove/[0.03]' : 'rule bg-raised'}`}>
      <p className="font-mono text-3xs uppercase tracking-[0.14em] text-meta mb-1">{label}</p>
      <p className="font-display font-bold text-sm mb-3">{arm.label}</p>
      <dl className="space-y-0">
        <DataRow label="Dispatch" value={policy.dispatch === 'demand_aware' ? 'Demand-aware' : 'Nearest available'} />
        <DataRow label="Vehicles" value={arm.fleet.vehicles} />
        <DataRow label="Chargers" value={arm.fleet.chargers} />
        <DataRow label="Airport priority" value={on(policy.airport_priority)} />
        <DataRow label="Battery reserve" value={`${Math.round(policy.airport_battery_reserve * 100)}%`} />
        <DataRow label="Repositioning" value={on(policy.demand_aware_repositioning)} />
        <DataRow label="Expansion zones" value={on(policy.service_area_expansion)} />
      </dl>
    </div>
  )
}

export default function Workspace({ detail }: { detail: ExperimentDetail }) {
  const router = useRouter()
  const [config, setConfig] = useState<ExperimentConfig>(detail.config)
  const [job, setJob] = useState<JobState>({ phase: 'idle' })
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [showYaml, setShowYaml] = useState(false)

  const patchProposed = useCallback(
    (fn: (c: ExperimentConfig) => void) => {
      setConfig((prev) => {
        const next: ExperimentConfig = JSON.parse(JSON.stringify(prev))
        fn(next)
        return next
      })
      setValidation(null)
    },
    [],
  )

  const dirty = useMemo(
    () => JSON.stringify(config) !== JSON.stringify(detail.config),
    [config, detail.config],
  )

  const run = useCallback(async () => {
    setJob({ phase: 'validating' })
    try {
      const v = await api.validate(config)
      setValidation(v)
      if (!v.valid) {
        setJob({ phase: 'error', message: 'Configuration is invalid. Fix the fields below and run again.' })
        return
      }
      setJob({ phase: 'running', step: `Sampling demand across ${config.run.replications} replications per arm` })
      const out = await api.run(config)
      router.push(`/experiments/${detail.config.id}/results?run=${encodeURIComponent(out.run_id)}`)
    } catch (e) {
      setJob({ phase: 'error', message: e instanceof ApiError ? e.message : 'The run failed.' })
    }
  }, [config, detail.config.id, router])

  const busy = job.phase === 'validating' || job.phase === 'running'

  return (
    <div className="grid lg:grid-cols-[1fr_360px] gap-8 lg:gap-10 items-start">
      <div className="min-w-0">
        <SectionLabel>Comparison</SectionLabel>
        <div className="grid sm:grid-cols-2 gap-3 mb-9">
          <ArmSummary label="Baseline" arm={config.baseline} tone="base" />
          <ArmSummary label="Proposed" arm={config.proposed} tone="prop" />
        </div>

        <SectionLabel id="assumptions-heading">Assumptions in force</SectionLabel>
        <Panel className="p-4 mb-9">
          <ul className="space-y-2 text-xs text-muted leading-relaxed">
            <li className="flex gap-2">
              <span aria-hidden="true" className="text-grove shrink-0">–</span>
              <span>Both arms see the <strong className="text-ink font-medium">same sampled demand</strong> per
              replication, so any difference between them is policy, not weather.</span>
            </li>
            <li className="flex gap-2">
              <span aria-hidden="true" className="text-grove shrink-0">–</span>
              <span>Demand is drawn from the model&apos;s own P10–P90 spread, centred on{' '}
              <strong className="text-ink font-medium uppercase">{config.demand.percentile}</strong>.
              Zones with uncertain forecasts move more than zones with tight ones.</span>
            </li>
            <li className="flex gap-2">
              <span aria-hidden="true" className="text-grove shrink-0">–</span>
              <span>Travel uses a circuity multiplier over straight-line distance, not a routing engine.
              Absolute pickup times are indicative; the comparison between arms is the signal.</span>
            </li>
            <li className="flex gap-2">
              <span aria-hidden="true" className="text-grove shrink-0">–</span>
              <span>Autonomous driving itself is out of scope. No perception, planning, or remote
              assistance is modelled.</span>
            </li>
          </ul>
        </Panel>

        <SectionLabel>Configuration</SectionLabel>
        <Panel className="p-4">
          <div className="flex items-center justify-between gap-4 mb-1">
            <p className="font-mono text-2xs text-meta">experiments/{config.id}.yaml</p>
            <button
              onClick={() => setShowYaml((s) => !s)}
              aria-expanded={showYaml}
              className="font-mono text-2xs text-grove hover:underline underline-offset-2"
            >
              {showYaml ? 'Hide' : 'Show'} source
            </button>
          </div>
          {showYaml && (
            <pre className="mt-3 font-mono text-3xs leading-relaxed bg-raised border rule rounded p-3 overflow-x-auto max-h-80 overflow-y-auto">
              {detail.yaml}
            </pre>
          )}
          {dirty && (
            <p className="mt-3 font-mono text-2xs text-signal-hold">
              Edited in session. The run will use your edits, not the file on disk.
            </p>
          )}
        </Panel>
      </div>

      {/* Controls rail */}
      <aside className="lg:sticky lg:top-20 min-w-0" aria-label="Experiment controls">
        <Panel className="p-4 mb-4">
          <SectionLabel>Proposed arm</SectionLabel>
          <Control
            id="vehicles" label="Fleet size" unit="vehicles"
            help="Vehicles available when the window opens."
            value={config.proposed.fleet.vehicles} min={80} max={420} step={10}
            onChange={(v) => patchProposed((c) => { c.proposed.fleet.vehicles = v })}
          />
          <Control
            id="chargers" label="Charger count" unit="stalls"
            help="Depot stalls shared across both depots. The binding constraint in most late-night scenarios."
            value={config.proposed.fleet.chargers} min={8} max={96} step={4}
            onChange={(v) => patchProposed((c) => { c.proposed.fleet.chargers = v })}
          />
          <Control
            id="reserve" label="Airport battery reserve" unit="%"
            help="Charge held back so a vehicle can still take an airport trip. Requires airport priority."
            value={Math.round(config.proposed.policy.airport_battery_reserve * 100)} min={0} max={40} step={5}
            onChange={(v) => patchProposed((c) => { c.proposed.policy.airport_battery_reserve = v / 100 })}
          />
          <Toggle
            id="expansion" label="Service-area expansion"
            help="Adds Eastvale, Foothill Park, and Lakeshore to the served area."
            checked={config.proposed.policy.service_area_expansion}
            onChange={(v) => patchProposed((c) => { c.proposed.policy.service_area_expansion = v })}
          />
          <Toggle
            id="airport-priority" label="Airport priority"
            help="Airport demand wins contested supply in both matching and repositioning."
            checked={config.proposed.policy.airport_priority}
            onChange={(v) => patchProposed((c) => {
              c.proposed.policy.airport_priority = v
              if (!v) c.proposed.policy.airport_battery_reserve = 0
            })}
          />
          <Toggle
            id="repositioning" label="Demand-aware repositioning"
            help="Moves idle vehicles toward forecast demand two intervals ahead."
            checked={config.proposed.policy.demand_aware_repositioning}
            onChange={(v) => patchProposed((c) => { c.proposed.policy.demand_aware_repositioning = v })}
          />
        </Panel>

        <Panel className="p-4 mb-4">
          <SectionLabel>Scenario</SectionLabel>
          <div className="py-3 border-b rule">
            <label htmlFor="percentile" className="text-sm font-medium text-ink block mb-1.5">
              Demand percentile
            </label>
            <div className="flex gap-1.5" role="radiogroup" aria-labelledby="percentile">
              {(['p10', 'p50', 'p90'] as const).map((p) => (
                <button
                  key={p}
                  role="radio"
                  aria-checked={config.demand.percentile === p}
                  onClick={() => patchProposed((c) => { c.demand.percentile = p })}
                  className={`flex-1 font-mono text-2xs uppercase py-1.5 rounded border transition-colors ${
                    config.demand.percentile === p
                      ? 'border-grove bg-grove/10 text-grove'
                      : 'rule text-meta hover:border-line-strong'
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>
            <p className="text-2xs text-meta mt-1.5 leading-relaxed">
              Which quantile centres the demand draw. P90 is the stress case.
            </p>
          </div>
          <Control
            id="replications" label="Replications" unit="per arm"
            help="Independent demand draws. More replications tighten the uncertainty band and cost runtime."
            value={config.run.replications} min={4} max={40} step={2}
            onChange={(v) => patchProposed((c) => { c.run.replications = v })}
          />
          <Toggle
            id="rain" label="Wet weather"
            help="Lifts demand and slows travel across every zone."
            checked={config.demand.rain}
            onChange={(v) => patchProposed((c) => { c.demand.rain = v })}
          />
          <Toggle
            id="event" label="Stadium event"
            help="A venue letting out mid-window, concentrated on two core zones."
            checked={config.demand.event_surge}
            onChange={(v) => patchProposed((c) => { c.demand.event_surge = v })}
          />
        </Panel>

        {validation && !validation.valid && (
          <Panel className="p-4 mb-4 border-signal-stop/40">
            <p className="font-mono text-2xs uppercase tracking-[0.14em] text-signal-stop mb-2">
              Schema validation failed
            </p>
            <ul className="space-y-1.5">
              {validation.errors.map((err, i) => (
                <li key={i} className="text-2xs">
                  <code className="font-mono text-ink">{err.path || '(root)'}</code>
                  <span className="text-muted"> — {err.message}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <button
          onClick={run}
          disabled={busy}
          className="w-full bg-ink text-canvas font-mono text-sm py-3 rounded-full hover:opacity-90 disabled:opacity-50 disabled:cursor-wait transition-opacity"
        >
          {job.phase === 'validating' ? 'Validating…' : job.phase === 'running' ? 'Running…' : 'Run experiment'}
        </button>

        <div aria-live="polite" className="mt-3 min-h-[2.5rem]">
          {job.phase === 'running' && (
            <p className="text-2xs text-muted leading-relaxed">
              {job.step}. Both arms run on identical draws; this takes a few seconds.
            </p>
          )}
          {job.phase === 'error' && (
            <p className="text-2xs text-signal-stop leading-relaxed">{job.message}</p>
          )}
        </div>

        <div className="mt-4 pt-4 border-t rule">
          <dl>
            <DataRow label="Window" value={`${DAY_NAMES[config.demand.day_of_week]} ${windowLabel(config.run.window_start_hour, config.run.horizon_minutes)}`} />
            <DataRow label="Seed" value={config.run.seed} />
            <DataRow label="Snapshot" value={detail.input_snapshot} />
          </dl>
          <SimulatedNotice className="mt-3" />
        </div>
      </aside>
    </div>
  )
}
