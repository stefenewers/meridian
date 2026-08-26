import Link from 'next/link'
import { notFound } from 'next/navigation'
import { api, ApiError } from '@/lib/api'
import Workspace from '@/components/workspace'
import { Panel, StatusChip } from '@/components/primitives'

export const dynamic = 'force-dynamic'

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  try {
    const detail = await api.experiment(id)
    return { title: detail.config.title }
  } catch {
    return { title: 'Experiment' }
  }
}

export default async function ExperimentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  let detail
  try {
    detail = await api.experiment(id)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound()
    return (
      <div className="max-w-site mx-auto px-5 md:px-8 py-12">
        <Panel className="p-6">
          <h1 className="font-display font-bold text-lg mb-2">Cannot load this experiment</h1>
          <p className="text-sm text-muted">{e instanceof ApiError ? e.message : 'Unknown error'}</p>
        </Panel>
      </div>
    )
  }

  const { config } = detail

  return (
    <div className="max-w-site mx-auto px-5 md:px-8 py-8 md:py-11">
      <nav aria-label="Breadcrumb" className="mb-6">
        <Link href="/" className="font-mono text-2xs text-meta hover:text-ink transition-colors">
          ← Scenario library
        </Link>
      </nav>

      <header className="mb-9 max-w-prose">
        <div className="flex items-center gap-3 mb-3">
          <StatusChip status={detail.status} />
          <span className="font-mono text-2xs text-meta">
            {detail.owner} · v{config.config_version}
          </span>
        </div>
        <h1 className="font-display font-extrabold text-[clamp(1.5rem,3vw,2.125rem)] leading-[1.12] tracking-tight mb-3">
          {config.title}
        </h1>
        <p className="text-base text-muted leading-relaxed">{config.question}</p>
      </header>

      <Workspace detail={detail} />
    </div>
  )
}
