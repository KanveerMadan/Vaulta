import { Link } from 'react-router-dom'

/** "vaulta.in" set in the display face, all lowercase, with the ledger rule under the v and the .in in green. */
export default function Wordmark({ to = '/', className = '', size = 'text-xl' }) {
  return (
    <Link to={to} className={`inline-flex items-baseline font-display font-semibold tracking-tight text-ink ${size} ${className}`} aria-label="vaulta.in home">
      <span className="relative">v<span aria-hidden className="absolute left-0 right-0 -bottom-0.5 h-[2px] bg-accent" /></span>aulta<span className="text-accent-text">.in</span>
    </Link>
  )
}
