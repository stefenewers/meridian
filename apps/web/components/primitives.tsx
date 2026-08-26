import type { ReactNode } from 'react'

/** Small labelled section header used across all three views. */
export function SectionLabel({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="font-mono text-2xs uppercase tracking-[0.16em] text-meta mb-3">
      {children}
    </h2>
  )
}

export function Panel({
  children,
  className = '',
  as: Tag = 'section',
}: {
  children: ReactNode
  className?: string
  as?: 'section' | 'div' | 'article'
}) {
  return (
    <Tag className={`bg-surface border rule rounded-card ${className}`}>{children}</Tag>
  )
}

/** Key/value row for assumption and provenance panels. */
export function DataRow({ label, value, mono = true }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 border-b rule last:border-b-0">
      <dt className="font-mono text-2xs text-meta shrink-0">{label}</dt>
      <dd className={`text-xs text-ink text-right ${mono ? 'font-mono nums' : ''}`}>{value}</dd>
    </div>
  )
}

const STATUS_STYLES: Record<string, string> = {
  draft: 'text-meta border-line',
  running: 'text-signal-info border-signal-info/30',
  decision_ready: 'text-signal-go border-signal-go/30',
}

const STATUS_LABEL: Record<string, string> = {
  draft: 'Draft',
  running: 'Running',
  decision_ready: 'Decision ready',
}

export function StatusChip({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-3xs uppercase tracking-[0.14em] border rounded-full px-2 py-0.5 ${
        STATUS_STYLES[status] ?? STATUS_STYLES.draft
      }`}
    >
      <span aria-hidden="true" className="w-1 h-1 rounded-full bg-current" />
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

/** Always-visible reminder that outputs are simulated. */
export function SimulatedNotice({ className = '' }: { className?: string }) {
  return (
    <p className={`font-mono text-3xs uppercase tracking-[0.14em] text-meta ${className}`}>
      Simulated output · synthetic demand · not observed performance
    </p>
  )
}
