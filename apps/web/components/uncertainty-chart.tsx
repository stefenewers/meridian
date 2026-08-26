'use client'

import {
  Bar, BarChart, CartesianGrid, Cell, Legend, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { RunOutput } from '@meridian/shared'

/**
 * Per-replication outcomes for the metric a decision turns on.
 *
 * A single mean would hide the thing that matters most here: the proposed arm can clear
 * its target on a typical night and still breach a guardrail on a busy one. Plotting each
 * replication makes the spread the reader's first impression rather than a footnote.
 */
export default function UncertaintyChart({
  run, metric, target, label, unit,
}: {
  run: RunOutput
  metric: string
  target?: number
  label: string
  unit: string
}) {
  const base = run.replication_samples[`baseline.${metric}`] ?? []
  const prop = run.replication_samples[`proposed.${metric}`] ?? []
  const data = base.map((b, i) => ({
    rep: `R${i + 1}`,
    baseline: Number(b.toFixed(2)),
    proposed: Number((prop[i] ?? 0).toFixed(2)),
  }))

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4 mb-2">
        <h3 className="text-sm font-medium text-ink">{label}</h3>
        <span className="font-mono text-3xs text-meta">{unit} · one bar pair per replication</span>
      </div>
      <div style={{ width: '100%', height: 210 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 6, right: 6, left: -18, bottom: 0 }} barGap={1}>
            <CartesianGrid strokeDasharray="2 4" stroke="rgba(0,0,0,0.07)" vertical={false} />
            <XAxis dataKey="rep" tick={{ fontSize: 9, fill: '#55504a' }} tickLine={false} axisLine={{ stroke: 'rgba(0,0,0,0.12)' }} interval={0} />
            <YAxis tick={{ fontSize: 10, fill: '#55504a' }} tickLine={false} axisLine={false} width={44} />
            <Tooltip
              cursor={{ fill: 'rgba(0,0,0,0.03)' }}
              contentStyle={{
                background: '#ffffff', border: '1px solid rgba(0,0,0,0.12)',
                borderRadius: 8, fontSize: 12, fontFamily: 'var(--font-dm-mono)',
              }}
              formatter={(v: number, n: string) => [`${v} ${unit}`, n === 'baseline' ? 'Baseline' : 'Proposed']}
            />
            <Legend
              verticalAlign="top" align="right" height={22}
              formatter={(v) => <span style={{ fontSize: 11, color: '#55504a' }}>{v === 'baseline' ? 'Baseline' : 'Proposed'}</span>}
            />
            {target !== undefined && (
              <ReferenceLine
                y={target} stroke="#8c2f22" strokeDasharray="4 3"
                label={{ value: `target ${target}`, position: 'insideTopRight', fontSize: 10, fill: '#8c2f22' }}
              />
            )}
            <Bar dataKey="baseline" fill="rgba(20,18,16,0.32)" radius={[2, 2, 0, 0]} />
            <Bar dataKey="proposed" radius={[2, 2, 0, 0]}>
              {data.map((d, i) => (
                <Cell
                  key={i}
                  fill={target !== undefined && d.proposed > target ? '#8c2f22' : '#1a6b3c'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
