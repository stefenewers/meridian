import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="max-w-site mx-auto px-5 md:px-8 py-16">
      <h1 className="font-display font-extrabold text-2xl mb-3">Not found</h1>
      <p className="text-sm text-muted mb-6">
        That experiment or run is not in the library.
      </p>
      <Link href="/" className="font-mono text-2xs text-grove hover:underline underline-offset-2">
        ← Scenario library
      </Link>
    </div>
  )
}
