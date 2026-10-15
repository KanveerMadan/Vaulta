import { useEffect, useRef } from 'react'
import { X } from '@phosphor-icons/react'

/**
 * Modal on desktop, bottom sheet on phones. Built on <dialog>: focus is trapped, Escape
 * closes, the page behind is inert. `onClose` runs for Escape, the close button and backdrop taps.
 */
export default function Sheet({ open = true, title, onClose, children, footer, wide = false }) {
  const ref = useRef(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])

  return (
    <dialog ref={ref} aria-label={title} onCancel={(e) => { e.preventDefault(); onClose?.() }}
      onClick={(e) => { if (e.target === ref.current) onClose?.() }}
      className={`sheet ${wide ? 'sm:max-w-2xl' : 'sm:max-w-lg'}`}>
      <div className="flex flex-col max-h-[inherit]">
        <header className="flex items-center justify-between gap-3 px-5 pt-4 pb-3">
          <h2 className="font-display text-xl text-ink">{title}</h2>
          <button onClick={onClose} className="btn-quiet w-10 h-10 !p-0" aria-label="Close"><X size={18} /></button>
        </header>
        <div className="px-5 pb-5 overflow-y-auto overscroll-contain">{children}</div>
        {footer && <footer className="px-5 py-3 border-t border-line flex gap-2 justify-end">{footer}</footer>}
      </div>
    </dialog>
  )
}
