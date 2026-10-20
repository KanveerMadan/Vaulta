import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, MagnifyingGlass, Plus, Sparkle } from '@phosphor-icons/react'
import api from '../lib/api'
import { parseQuickAdd } from '../lib/quickAdd'
import { addManualTransaction } from '../lib/transactions'
import { useCommandPalette } from '../lib/commands'
import { useFinanceStore } from '../store/financeStore'
import { formatINR } from '../lib/money'
import { toast } from '../lib/toast'

const PAGES = [
  ['Home', '/'], ['Transactions', '/transactions'], ['Budgets', '/budgets'], ['Goals', '/goals'], ['Cash', '/cash'],
  ['Recurring', '/recurring'], ['Reports', '/reports'], ['People', '/people'], ['Rules', '/rules'], ['Connect', '/connect'],
  ['Settings', '/settings'], ['Review questions', '/review'],
]

/**
 * ⌘K / Ctrl+K: search transactions, jump to a page, quick-add ("450 swiggy"), or ask the assistant.
 * A combobox: type, move with ↑ ↓, run with Enter, close with Escape.
 */
export default function CommandPalette() {
  const { isOpen, close, toggle } = useCommandPalette()
  const navigate = useNavigate()
  const ask = useFinanceStore((s) => s.ask)
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const [matches, setMatches] = useState([])
  const dialog = useRef(null)

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); toggle() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggle])

  useEffect(() => {
    const d = dialog.current
    if (!d) return
    if (isOpen && !d.open) d.showModal()
    if (!isOpen && d.open) d.close()
  }, [isOpen])

  // merchants matching what's typed, from the server
  useEffect(() => {
    const term = q.trim()
    if (term.length < 2 || /^\d/.test(term)) return undefined
    let alive = true
    const id = setTimeout(() => {
      api.get(`/api/transactions?merchant=${encodeURIComponent(term)}&page_size=5`)
        .then(({ data }) => alive && setMatches(data.items))
        .catch(() => alive && setMatches([]))
    }, 180)
    return () => { alive = false; clearTimeout(id) }
  }, [q])

  const term = q.trim()
  const shownMatches = term.length < 2 || /^\d/.test(term) ? [] : matches
  const parsed = term ? parseQuickAdd(term) : null
  const items = (() => {
    const out = []
    if (parsed) out.push({ id: 'add', icon: Plus, label: `Add ${formatINR(parsed.amount)} ${parsed.merchant}`, hint: `${parsed.category || 'auto category'} · ${parsed.payment_method}`, run: async () => {
      try { await addManualTransaction(parsed); toast(`Added ${parsed.merchant}, ${formatINR(parsed.amount)}.`) } catch { toast({ tone: 'danger', message: "Couldn't add that." }) }
    } })
    for (const t of shownMatches) {
      out.push({ id: `t-${t.id}`, icon: MagnifyingGlass, label: t.merchant_clean || t.merchant_raw, hint: `${formatINR(t.amount)} · ${new Date(t.transaction_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}`,
        run: () => navigate(`/transactions?q=${encodeURIComponent(t.merchant_clean || term)}`) })
    }
    for (const [label, to] of PAGES) {
      if (!term || label.toLowerCase().includes(term.toLowerCase())) out.push({ id: `p-${to}`, icon: ArrowRight, label: `Go to ${label}`, run: () => navigate(to) })
    }
    if (term) out.push({ id: 'ask', icon: Sparkle, label: `Ask: “${term}”`, hint: 'vaulta.in assistant', run: () => ask(term) })
    return out
  })()

  const finish = () => { close(); setQ(''); setActive(0) }
  const run = async (item) => { finish(); await item?.run() }
  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(0, a - 1)) }
    else if (e.key === 'Enter') { e.preventDefault(); run(items[Math.min(active, items.length - 1)]) }
  }

  return (
    <dialog ref={dialog} aria-label="Search and commands" className="palette" onCancel={(e) => { e.preventDefault(); finish() }}
      onClick={(e) => { if (e.target === dialog.current) finish() }}>
      <div className="flex items-center gap-2 px-4 border-b border-line">
        <MagnifyingGlass size={18} className="text-muted shrink-0" aria-hidden />
        <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setActive(0) }} onKeyDown={onKeyDown}
          role="combobox" aria-expanded="true" aria-controls="palette-list" aria-activedescendant={items[active] ? `pi-${items[active].id}` : undefined}
          placeholder="Search, go to, “450 swiggy”, or ask…" spellCheck={false}
          className="flex-1 h-14 bg-transparent text-[15px] text-ink placeholder:text-muted outline-none" />
        <kbd className="kbd">esc</kbd>
      </div>
      <ul id="palette-list" role="listbox" aria-label="Results" className="max-h-[min(60dvh,26rem)] overflow-y-auto p-2">
        {items.map((it, i) => (
          <li key={it.id} id={`pi-${it.id}`} role="option" aria-selected={i === active} onMouseMove={() => setActive(i)} onClick={() => run(it)}
            className={`flex items-center gap-3 rounded-sm px-3 py-2.5 cursor-pointer text-sm ${i === active ? 'bg-accent-tint text-ink' : 'text-ink-2'}`}>
            <it.icon size={16} className="shrink-0 text-muted" aria-hidden />
            <span className="flex-1 truncate">{it.label}</span>
            {it.hint && <span className="text-micro text-muted shrink-0">{it.hint}</span>}
          </li>
        ))}
        {!items.length && <li className="px-3 py-6 text-sm text-muted text-center">Nothing matches. Press Enter to ask the assistant.</li>}
      </ul>
    </dialog>
  )
}
