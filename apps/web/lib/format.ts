/** Number formatting for a decision surface: consistent precision, explicit units. */

export function minutes(v: number, dp = 1): string {
  return `${v.toFixed(dp)} min`
}

export function pct(v: number, dp = 1): string {
  return `${(v * 100).toFixed(dp)}%`
}

export function points(v: number, dp = 1): string {
  const s = v >= 0 ? '+' : ''
  return `${s}${(v * 100).toFixed(dp)} pts`
}

export function money(v: number): string {
  return `$${v.toFixed(2)}`
}

export function count(v: number): string {
  return Math.round(v).toLocaleString('en-US')
}

export function delta(base: number, prop: number, dp = 1): string {
  const d = prop - base
  return `${d >= 0 ? '+' : ''}${d.toFixed(dp)}`
}

export function deltaPct(base: number, prop: number): string {
  if (base === 0) return '—'
  const d = ((prop - base) / Math.abs(base)) * 100
  return `${d >= 0 ? '+' : ''}${d.toFixed(1)}%`
}

export const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export function windowLabel(startHour: number, horizonMinutes: number): string {
  const end = (startHour + horizonMinutes / 60) % 24
  const fmt = (h: number) => `${String(Math.floor(h)).padStart(2, '0')}:00`
  return `${fmt(startHour)}–${fmt(end)}`
}
