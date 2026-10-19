import { useEffect } from 'react'
import { X } from '@phosphor-icons/react'
import { useToasts } from '../lib/toast'

const LIFETIME_MS = 6000

function Item({ t }) {
  const dismiss = useToasts((s) => s.dismiss)
  useEffect(() => {
    const id = setTimeout(() => dismiss(t.id), t.action ? LIFETIME_MS * 1.5 : LIFETIME_MS)
    return () => clearTimeout(id)
  }, [t, dismiss])
  return (
    <div className={`pointer-events-auto flex items-center gap-3 rounded-md px-4 py-3 shadow-3 text-sm animate-rise
      ${t.tone === 'danger' ? 'bg-danger text-on-inverse' : 'bg-inverse text-on-inverse'}`}>
      <span className="flex-1">{t.message}</span>
      {t.action && (
        <button className="font-semibold underline underline-offset-2" onClick={() => { t.action.onClick(); dismiss(t.id) }}>{t.action.label}</button>
      )}
      <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="opacity-70 hover:opacity-100"><X size={16} /></button>
    </div>
  )
}

/** Mounted once (App). Announced politely to screen readers. */
export function Toaster() {
  const items = useToasts((s) => s.items)
  return (
    <div role="status" aria-live="polite" className="fixed bottom-safe-20 lg:bottom-6 left-1/2 -translate-x-1/2 z-[70] w-[min(28rem,calc(100vw-2rem))] flex flex-col gap-2 pointer-events-none">
      {items.map((t) => <Item key={t.id} t={t} />)}
    </div>
  )
}
