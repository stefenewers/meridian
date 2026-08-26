import Link from 'next/link'
import { api, ApiError } from '@/lib/api'
import Results from '@/components/results'
import { Panel } from '@/components/primitives'

export const dynamic = 'force-dynamic'

export const metadata = { title: 'Results' }

export default async function ResultsPage({
  params, searchParams,
}: {
  params: Promise<{ id: string }>
  searchParams: Promise<{ run?: string }>
}) {
  const { id } = await params
  const { run: runId } = await searchParams

  if (!runId) {
    return (
      <div className="max-w-site mx-auto px-5 md:px-8 py-12">
        <Panel className="p-6">
          <h1 className="font-display font-bold text-lg mb-2">No run selected</h1>
          <p className="text-sm text-muted mb-4">
            Results are tied to a specific run id, so the numbers on this page always belong to a
            known configuration and seed.
          </p>
          <Link href={`/experiments/${id}`} className="font-mono text-2xs text-grove hover:underline underline-offset-2">
            ← Open the workspace and run the experiment
          </Link>
        </Panel>
      </div>
    )
  }

  let run
  try {
    run = await api.getRun(runId)
  } catch (e) {
    return (
      <div className="max-w-site mx-auto px-5 md:px-8 py-12">
        <Panel className="p-6">
          <h1 className="font-display font-bold text-lg mb-2">That run is not available</h1>
          <p className="text-sm text-muted mb-4">
            {e instanceof ApiError ? e.message : 'Unknown error'} Runs are held in the simulation
            service&apos;s memory, so restarting it clears them. Re-run the experiment to get a new
            run id.
          </p>
          <Link href={`/experiments/${id}`} className="font-mono text-2xs text-grove hover:underline underline-offset-2">
            ← Back to workspace
          </Link>
        </Panel>
      </div>
    )
  }

  return (
    <div className="max-w-site mx-auto px-5 md:px-8 py-8 md:py-11">
      <nav aria-label="Breadcrumb" className="mb-6 flex flex-wrap gap-x-2 items-center">
        <Link href="/" className="font-mono text-2xs text-meta hover:text-ink transition-colors">Scenario library</Link>
        <span aria-hidden="true" className="font-mono text-2xs text-meta">/</span>
        <Link href={`/experiments/${id}`} className="font-mono text-2xs text-meta hover:text-ink transition-colors">
          {run.config.title}
        </Link>
        <span aria-hidden="true" className="font-mono text-2xs text-meta">/</span>
        <span className="font-mono text-2xs text-ink">Results</span>
      </nav>

      <header className="mb-8 max-w-prose">
        <h1 className="font-display font-extrabold text-[clamp(1.5rem,3vw,2.125rem)] leading-[1.12] tracking-tight mb-3">
          {run.config.title}
        </h1>
        <p className="text-base text-muted leading-relaxed">{run.config.question}</p>
      </header>

      <Results run={run} />
    </div>
  )
}
