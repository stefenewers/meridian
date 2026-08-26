/**
 * The one place the UI talks to the simulation service.
 *
 * Errors are returned rather than thrown where a view can render a useful empty state:
 * an operations tool that shows a blank screen because a service is down is worse than
 * one that says which service and what to run.
 */

import type {
  ExperimentConfig,
  ExperimentSummary,
  RunOutput,
  ValidationResult,
} from '@meridian/shared'

export const API_BASE =
  process.env.NEXT_PUBLIC_MERIDIAN_API ?? 'http://127.0.0.1:8000'

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function get<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: 'no-store' })
  } catch {
    throw new ApiError(
      `Cannot reach the simulation service at ${API_BASE}. Start it with: make api`,
    )
  }
  if (!res.ok) throw new ApiError(`${path} returned ${res.status}`, res.status)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError(
      `Cannot reach the simulation service at ${API_BASE}. Start it with: make api`,
    )
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new ApiError(detail || `${path} returned ${res.status}`, res.status)
  }
  return res.json() as Promise<T>
}

export interface ExperimentDetail {
  config: ExperimentConfig
  yaml: string
  status: ExperimentSummary['status']
  owner: string
  input_snapshot: string
  runs: string[]
}

export const api = {
  health: () => get<{ status: string; demand_model_trained: boolean }>('/health'),
  experiments: () => get<ExperimentSummary[]>('/experiments'),
  experiment: (id: string) => get<ExperimentDetail>(`/experiments/${id}`),
  validate: (config: unknown) => post<ValidationResult>('/experiments/validate', config),
  run: (config: ExperimentConfig) => post<RunOutput>('/runs', { config }),
  getRun: (runId: string) => get<RunOutput>(`/runs/${runId}`),
}
