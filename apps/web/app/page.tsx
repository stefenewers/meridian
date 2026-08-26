import Link from 'next/link'
import { api, ApiError } from '@/lib/api'
import { Panel, SectionLabel, StatusChip } from '@/components/primitives'
import type { ExperimentSummary } from '@meridian/shared'

export const dynamic = 'force-dynamic'

function ServiceDown({ message }: { message: string }) {
  return (
    <Panel className="p-6">
      <h2 className="font-display font-bold text-lg mb-2">The simulation service is not responding</h2>
      <p className="text-sm text-muted mb-4 max-w-prose">{message}</p>
      <pre className="font-mono text-2xs bg-raised border rule rounded p-3 overflow-x-auto">
        cd services/simulation{'\n'}
        python -m venv .venv &amp;&amp; ./.venv/bin/pip install -r requirements.txt{'\n'}
        ./.venv/bin/python scripts/train_demand_model.py{'\n'}
        ./.venv/bin/uvicorn meridian.api:app --port 8000
      </pre>
    </Panel>
  )
}

export default async function ScenarioLibrary() {
  let experiments: ExperimentSummary[] = []
  let error: string | null = null
  try {
    experiments = await api.experiments()
  } catch (e) {
    error = e instanceof ApiError ? e.message : 'Unknown error'
  }

  return (
    <div className="max-w-site mx-auto px-5 md:px-8 py-10 md:py-14">
      <div className="max-w-prose mb-10 md:mb-14">
        <h1 className="font-display font-extrabold text-[clamp(1.75rem,3.4vw,2.5rem)] leading-[1.1] tracking-tight mb-4">
          Test fleet, depot, and dispatch changes before production rollout.
        </h1>
        <p className="text-base text-muted leading-relaxed">
          Each scenario pairs a baseline against a proposed change, runs both against the same
          sampled demand, and reports what moves, what breaks, and how confident the result is.
        </p>
      </div>

      <SectionLabel id="library-heading">Scenario library</SectionLabel>

      {error ? (
        <ServiceDown message={error} />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2" aria-labelledby="library-heading">
          {experiments.map((exp) => (
            <li key={exp.id}>
              <Link
                href={`/experiments/${exp.id}`}
                className="group block h-full bg-surface border rule rounded-card p-5 hover:border-line-strong transition-colors"
              >
                <div className="flex items-start justify-between gap-3 mb-2.5">
                  <h3 className="font-display font-bold text-[17px] leading-snug">{exp.title}</h3>
                  <StatusChip status={exp.status} />
                </div>
                <p className="text-sm text-muted leading-relaxed mb-5">{exp.question}</p>
                <dl className="grid grid-cols-3 gap-3 pt-3 border-t rule">
                  <div>
                    <dt className="font-mono text-3xs uppercase tracking-[0.14em] text-meta">Owner</dt>
                    <dd className="font-mono text-2xs text-ink mt-0.5">{exp.owner}</dd>
                  </div>
                  <div>
                    <dt className="font-mono text-3xs uppercase tracking-[0.14em] text-meta">Version</dt>
                    <dd className="font-mono text-2xs text-ink mt-0.5 nums">v{exp.config_version}</dd>
                  </div>
                  <div>
                    <dt className="font-mono text-3xs uppercase tracking-[0.14em] text-meta">Runs</dt>
                    <dd className="font-mono text-2xs text-ink mt-0.5 nums">
                      {exp.run_count > 0 ? exp.run_count : '—'}
                    </dd>
                  </div>
                </dl>
                <span className="mt-4 inline-flex items-center gap-1.5 font-mono text-2xs text-grove">
                  Open workspace
                  <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">→</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
