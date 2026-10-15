import { useEffect, useState } from 'react'

// Live numbers for the landing page, from the read-only demo account through the real API
// (the same analytics the app and the chat use). Fetched once, only when a section that
// needs them comes near the viewport, with a token kept here, never in the app's sign-in state.
const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
let pending = null

async function load() {
  const res = await fetch(`${API}/auth/demo`, { method: 'POST' })
  if (!res.ok) throw new Error('demo unavailable')
  const { token } = await res.json()
  const get = (path) => fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } }).then((r) => (r.ok ? r.json() : null))
  const [home, summary, reports] = await Promise.all([get('/api/home'), get('/api/transactions/summary?period=month'), get('/api/reports')])
  const monthly = (Array.isArray(reports) ? reports : []).find((r) => r.period_type === 'monthly')
  const report = monthly ? await get(`/api/reports/${monthly.id}`) : null
  return { home, summary, report }
}

export function useDemoSnapshot(ref) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const io = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return
      io.disconnect()
      pending = pending || load()
      pending.then(setData).catch(() => { pending = null; setFailed(true) })
    }, { rootMargin: '600px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [ref])
  return { data, failed }
}
