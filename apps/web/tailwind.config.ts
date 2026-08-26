import type { Config } from 'tailwindcss'

/**
 * Meridian's palette is a sibling of stefenewers.com, not a copy. The cream ground and
 * green accent carry over so the two read as the same hand. The product adds a colder
 * ink, a denser type scale, and a signal set for verdicts, because an operations tool has
 * to say "this is a risk" without relying on decoration.
 */
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: '#f5f3ef',
        surface: '#ffffff',
        raised: '#fbfaf8',
        ink: '#141210',
        muted: '#625d56',
        meta: '#55504a',
        grove: { DEFAULT: '#1a6b3c', dark: '#2d9e5f' },
        // Verdict signals. Deliberately desaturated: this is a decision tool, not a dashboard.
        signal: {
          go: '#1a6b3c',
          hold: '#8a6a12',
          stop: '#8c2f22',
          info: '#1a4d6b',
        },
        line: { DEFAULT: 'rgba(0,0,0,0.10)', strong: 'rgba(0,0,0,0.18)' },
      },
      fontFamily: {
        display: ['var(--font-syne)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-dm-mono)', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '3xs': ['0.625rem', { lineHeight: '0.9rem' }],
        '2xs': ['0.75rem', { lineHeight: '1.15rem' }],
        xs: ['0.8125rem', { lineHeight: '1.15rem' }],
        sm: ['0.9375rem', { lineHeight: '1.5rem' }],
      },
      maxWidth: { site: '1180px', prose: '68ch' },
      borderRadius: { card: '10px' },
    },
  },
  plugins: [],
}
export default config
