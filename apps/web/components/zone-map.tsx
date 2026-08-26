'use client'

import type { RunOutput } from '@meridian/shared'

/**
 * A schematic of the service area, not a map.
 *
 * Meridian Bay is invented, so drawing it over real cartography would imply a real
 * market. Zones are placed on their abstract coordinates and sized by demand; fill
 * encodes completion rate. The point is to show which parts of the service area the
 * change helps and which it strains, which a choropleth of a real city would obscure.
 */
export default function ZoneMap({ run, arm }: { run: RunOutput; arm: 'baseline' | 'proposed' }) {
  const zones = run.zones
  const service = arm === 'baseline' ? run.baseline_zones : run.proposed_zones
  const expansionOn = run.config[arm].policy.service_area_expansion

  const xs = zones.map((z) => z.x)
  const ys = zones.map((z) => z.y)
  const pad = 1.5
  const minX = Math.min(...xs) - pad
  const maxX = Math.max(...xs) + pad
  const minY = Math.min(...ys) - pad
  const maxY = Math.max(...ys) + pad
  const w = maxX - minX
  const h = maxY - minY

  const fill = (rate: number | undefined) => {
    if (rate === undefined) return 'rgba(0,0,0,0.04)'
    // Completion rate mapped to green opacity. Deliberately coarse: a fine gradient
    // would imply precision the simulation does not have.
    const t = Math.max(0, Math.min(1, (rate - 0.6) / 0.4))
    return `rgba(26,107,60,${(0.10 + t * 0.55).toFixed(3)})`
  }

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full h-auto bg-raised border rule rounded-card"
        role="img"
        aria-label={`Zone service schematic for the ${arm} arm of Meridian Bay, a fictional service area.`}
      >
        <g transform={`translate(${-minX}, ${-minY})`}>
          {zones.map((z) => {
            const served = z.tier !== 'expansion' || expansionOn
            const s = service[z.id]
            // Radius must stay under half the minimum inter-zone distance or the schematic
            // reads as overlap rather than as relative volume.
            const r = 0.28 + Math.sqrt(s?.requested ?? 6) * 0.024
            return (
              <g key={z.id}>
                <circle
                  cx={z.x} cy={z.y} r={r}
                  fill={served ? fill(s?.completion_rate) : 'rgba(0,0,0,0.03)'}
                  stroke={
                    z.tier === 'airport' ? '#1a4d6b'
                      : z.tier === 'expansion' ? (served ? '#1a6b3c' : 'rgba(0,0,0,0.18)')
                      : 'rgba(0,0,0,0.28)'
                  }
                  strokeWidth={z.tier === 'core' ? 0.035 : 0.06}
                  strokeDasharray={z.tier === 'expansion' && !served ? '0.12 0.1' : undefined}
                />
                <text
                  x={z.x} y={z.y + r + 0.42}
                  textAnchor="middle"
                  style={{ fontSize: 0.32, fill: served ? '#55504a' : 'rgba(0,0,0,0.3)' }}
                  className="font-mono"
                >
                  {z.id}
                </text>
                {served && s && (
                  <text
                    x={z.x} y={z.y + 0.11}
                    textAnchor="middle"
                    style={{ fontSize: 0.34, fill: '#141210', fontWeight: 600 }}
                    className="font-mono"
                  >
                    {Math.round(s.completion_rate * 100)}
                  </text>
                )}
              </g>
            )
          })}
        </g>
      </svg>
      <figcaption className="mt-2.5 flex flex-wrap gap-x-5 gap-y-1 font-mono text-3xs text-meta">
        <span>Numbers are completion rate (%)</span>
        <span>Circle size = requests</span>
        <span>Dashed = outside service area</span>
        <span>Blue ring = airport</span>
      </figcaption>
    </figure>
  )
}
