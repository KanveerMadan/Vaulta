import { Link } from 'react-router-dom'

/** "Vaulta" set in the display face, with the ledger rule under the V. */
export default function Wordmark({ to = '/', className = '', size = 'text-xl' }) {
  return (
    <Link to={to} className={`inline-flex items-baseline font-display font-semibold tracking-tight text-ink ${size} ${className}`} aria-label="Vaulta home">
      <span className="relative">V<span aria-hidden className="absolute left-0 right-0 -bottom-0.5 h-[2px] bg-accent" /></span>aulta
    </Link>
  )
}
