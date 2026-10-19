import { useId } from 'react'

/** Label above, control, optional hint and error below. The control gets the ids it needs. */
export default function Field({ label, hint, error, children, className = '' }) {
  const id = useId()
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined
  const control = typeof children === 'function'
    ? children({ id, 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined })
    : children
  return (
    <div className={`space-y-1.5 ${className}`}>
      <label htmlFor={id} className="label">{label}</label>
      {control}
      {hint && <p id={`${id}-hint`} className="text-micro text-muted">{hint}</p>}
      {error && <p id={`${id}-error`} className="text-micro text-danger" role="alert">{error}</p>}
    </div>
  )
}
