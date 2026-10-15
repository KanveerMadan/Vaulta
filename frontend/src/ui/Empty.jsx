import { Link } from 'react-router-dom'

/** An empty state that says what to do next. */
export default function Empty({ icon: Icon, title, children, to, cta, onAction }) {
  return (
    <div className="flex items-start gap-3 py-2">
      {Icon && <span className="mt-0.5 shrink-0 w-9 h-9 rounded-sm bg-sunken text-muted flex items-center justify-center"><Icon size={18} /></span>}
      <div className="space-y-1 min-w-0">
        {title && <p className="text-sm font-medium text-ink">{title}</p>}
        <p className="text-sm text-muted">{children}</p>
        {to && <Link to={to} className="text-sm font-medium text-accent-text hover:underline">{cta}</Link>}
        {onAction && <button onClick={onAction} className="text-sm font-medium text-accent-text hover:underline">{cta}</button>}
      </div>
    </div>
  )
}
