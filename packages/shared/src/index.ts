/**
 * Types shared between the UI and the simulation service.
 *
 * These mirror the pydantic models in `services/simulation/meridian/config.py`. The
 * Python side is authoritative: it validates every request, and `/experiments/validate`
 * is what the config editor shows errors from. Duplicating the shapes here buys editor
 * support in the UI without pretending TypeScript is enforcing anything at runtime.
 */

export type DispatchPolicy = 'nearest_available' | 'demand_aware'
export type Percentile = 'p10' | 'p50' | 'p90'
export type Verdict = 'launch' | 'pilot' | 'do_not_launch'
export type ZoneTier = 'core' | 'airport' | 'expansion'
export type ExperimentStatus = 'draft' | 'running' | 'decision_ready'

export interface FleetConfig {
  vehicles: number
  depots: number
  chargers: number
  starting_soc: number
}

export interface PolicyConfig {
  dispatch: DispatchPolicy
  airport_priority: boolean
  airport_battery_reserve: number
  demand_aware_repositioning: boolean
  service_area_expansion: boolean
}

export interface ArmConfig {
  label: string
  fleet: FleetConfig
  policy: PolicyConfig
}

export interface DemandConfig {
  percentile: Percentile
  rain: boolean
  event_surge: boolean
  day_of_week: number
}

export interface RunConfig {
  replications: number
  seed: number
  horizon_minutes: number
  window_start_hour: number
}

export interface Targets {
  p50_pickup_minutes: number
  p90_pickup_minutes: number
  max_completion_loss_pct: number
  max_charger_queue_minutes: number
}

export interface ExperimentConfig {
  id: string
  title: string
  question: string
  owner: string
  config_version: string
  baseline: ArmConfig
  proposed: ArmConfig
  demand: DemandConfig
  run: RunConfig
  targets: Targets
}

/** Every metric is reported as a band across replications, never as a point. */
export interface Interval {
  mean: number
  p10: number
  p50: number
  p90: number
}

export interface Finding {
  kind: 'win' | 'risk' | 'neutral'
  metric: string
  headline: string
  detail: string
}

export interface Recommendation {
  verdict: Verdict
  label: string
  summary: string
  findings: Finding[]
  guardrails: string[]
}

export interface Provenance {
  seed: number
  replications: number
  input_snapshot: string
  config_version: string
  policy_version: string
  demand_model_version: string
  sim_engine_version: string
  package_version: string
  demand_model_metrics: Record<string, number>
  interval_minutes: number
  disclaimer: string
}

export interface Zone {
  id: string
  name: string
  x: number
  y: number
  tier: ZoneTier
}

export interface ZoneService {
  requested: number
  completed: number
  canceled: number
  completion_rate: number
  mean_pickup_minutes: number
}

export interface RunOutput {
  run_id: string
  experiment_id: string
  created_at: number
  config: ExperimentConfig
  baseline: Record<string, Interval>
  proposed: Record<string, Interval>
  baseline_zones: Record<string, ZoneService>
  proposed_zones: Record<string, ZoneService>
  zones: Zone[]
  recommendation: Recommendation
  provenance: Provenance
  replication_samples: Record<string, number[]>
}

export interface ExperimentSummary {
  id: string
  title: string
  question: string
  owner: string
  status: ExperimentStatus
  config_version: string
  replications: number
  run_count: number
  latest_run_id: string | null
}

export interface ValidationError {
  path: string
  message: string
  type: string
}

export interface ValidationResult {
  valid: boolean
  errors: ValidationError[]
  input_snapshot?: string
}
