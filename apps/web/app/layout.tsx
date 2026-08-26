import type { Metadata } from 'next'
import { Syne, DM_Mono } from 'next/font/google'
import Link from 'next/link'
import './globals.css'

const syne = Syne({ subsets: ['latin'], weight: ['400', '600', '700', '800'], variable: '--font-syne', display: 'swap' })
const dmMono = DM_Mono({ subsets: ['latin'], weight: ['300', '400', '500'], variable: '--font-dm-mono', display: 'swap' })

export const metadata: Metadata = {
  title: { default: 'Meridian — Fleet experimentation', template: '%s · Meridian' },
  description:
    'Test fleet, depot, and dispatch changes against service, cost, and reliability outcomes before production rollout.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${syne.variable} ${dmMono.variable}`}>
      <body className="min-h-screen flex flex-col">
        {/* Skip link: the first tab stop on every page. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-3 focus:left-3 focus:bg-ink focus:text-canvas focus:px-4 focus:py-2 focus:rounded-full focus:font-mono focus:text-2xs"
        >
          Skip to content
        </a>

        <header className="border-b rule sticky top-0 z-40 bg-canvas/90 backdrop-blur-md">
          <div className="max-w-site mx-auto px-5 md:px-8 h-14 flex items-center gap-6">
            <Link href="/" className="flex items-baseline gap-2.5 hover:opacity-80 transition-opacity">
              <span className="font-display font-extrabold tracking-tight text-[17px]">Meridian</span>
              <span className="font-mono text-3xs uppercase tracking-[0.18em] text-meta hidden sm:inline">
                Fleet experimentation
              </span>
            </Link>
            <nav aria-label="Primary" className="ml-auto flex items-center gap-5">
              <Link href="/" className="font-mono text-2xs uppercase tracking-widest text-meta hover:text-ink transition-colors">
                Scenarios
              </Link>
              <a
                href="https://github.com/stefenewers/meridian"
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-2xs uppercase tracking-widest text-meta hover:text-ink transition-colors"
              >
                Source
              </a>
            </nav>
          </div>
        </header>

        <main id="main" className="flex-1">{children}</main>

        <footer className="border-t rule mt-16">
          <div className="max-w-site mx-auto px-5 md:px-8 py-5 flex flex-wrap gap-x-6 gap-y-1.5 items-center">
            <p className="font-mono text-3xs uppercase tracking-[0.16em] text-meta">
              Meridian is a fictional product
            </p>
            <p className="text-2xs text-meta">
              All figures are simulated output from synthetic demand. Not affiliated with, derived
              from, or representative of any real ride-hail operator.
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
