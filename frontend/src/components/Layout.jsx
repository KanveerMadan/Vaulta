import { useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useApi } from '../lib/format'
import { signOut } from 'firebase/auth'
import { auth } from '../lib/firebase'
import { useAuthStore } from '../store/authStore'
import ChatPanel from './ChatPanel'
import AlertsBell from './AlertsBell'
import { useFinanceStore } from '../store/financeStore'

const NAV = [
  { to: '/', label: 'Home', end: true },
  { to: '/budgets', label: 'Budgets' },
  { to: '/goals', label: 'Goals' },
  { to: '/cash', label: 'Cash' },
  { to: '/recurring', label: 'Recurring' },
  { to: '/reports', label: 'Reports' },
  { to: '/people', label: 'People' },
  { to: '/rules', label: 'Rules' },
  { to: '/connect', label: 'Connect' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
  const { logout, user, demoToken, endDemo } = useAuthStore()
  const navigate = useNavigate()
  const [readOnly, setReadOnly] = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const { chatOpen, setChatOpen } = useFinanceStore()

  useEffect(() => {
    const show = (e) => setReadOnly(e.detail || "The demo is read-only.")
    window.addEventListener('vaulta:read-only', show)
    return () => window.removeEventListener('vaulta:read-only', show)
  }, [])
  useEffect(() => {
    if (!readOnly) return undefined
    const t = setTimeout(() => setReadOnly(null), 5000)
    return () => clearTimeout(t)
  }, [readOnly])

  const handleLogout = async () => {
    if (demoToken) endDemo()
    else await signOut(auth)
    logout()
    navigate('/welcome')
  }
  const signUp = () => { endDemo(); navigate('/login') }

  // First login: start setup (skippable; Settings → Resume setup brings it back)
  const { data: onboarding } = useApi('/api/onboarding', 0)
  useEffect(() => {
    if (onboarding?.status === 'new') navigate('/onboarding', { replace: true })
  }, [onboarding, navigate])

  const initial = (user?.displayName?.[0] || user?.email?.[0] || 'U').toUpperCase()

  return (
    <div className="min-h-dvh flex flex-col" style={{ background: '#F2F7F3' }}>
      {demoToken && (
        <div role="note" className="bg-gold/15 text-ink-900 text-sm px-4 py-2 text-center">
          You're viewing a demo with sample data.{' '}
          <button onClick={signUp} className="font-semibold underline underline-offset-2">Sign up to track your own.</button>
        </div>
      )}
      {readOnly && (
        <div role="alert" className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-ink-900 text-white text-sm rounded-xl shadow-lg px-4 py-3 max-w-[calc(100vw-2rem)]">
          {readOnly}
        </div>
      )}
      {/* Header: full nav from lg up; a menu button below */}
      <header className="sticky top-0 z-30 bg-white border-b border-sage-200"
        style={{ boxShadow: '0 1px 3px rgba(45,106,79,0.06)' }}>
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-2">
          <button onClick={() => setMenuOpen((v) => !v)} aria-expanded={menuOpen} aria-controls="main-nav"
            className="lg:hidden w-11 h-11 -ml-2 flex items-center justify-center rounded-lg text-ink-700 hover:bg-sage-100" aria-label="Menu">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
              {menuOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
          <span className="font-display text-lg font-light tracking-tight mr-2" style={{ color: '#1A2E1E' }}>Vaulta</span>

          <nav id="main-nav" aria-label="Main"
            className={`${menuOpen ? 'flex' : 'hidden'} lg:flex flex-col lg:flex-row absolute lg:static top-14 left-0 right-0 bg-white lg:bg-transparent border-b lg:border-0 border-sage-200 p-2 lg:p-0 gap-1 shadow-card lg:shadow-none`}>
            {NAV.map(({ to, label, end }) => (
              <NavLink key={to} to={to} end={end} onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  `px-3 py-3 lg:py-1.5 rounded-lg text-sm whitespace-nowrap transition-all duration-150 font-medium ${
                    isActive ? 'bg-forest-50 text-forest-400' : 'text-ink-500 hover:text-ink-700 hover:bg-sage-100'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1 sm:gap-3">
            <AlertsBell />
            <span className="text-ink-300 text-xs hidden sm:block truncate max-w-[160px]">
              {demoToken ? 'Demo' : user?.displayName || user?.email}
            </span>
            <div className="w-7 h-7 rounded-full hidden sm:flex items-center justify-center shrink-0 text-xs font-semibold"
              style={{ background: '#E8F5EB', color: '#2D6A4F', border: '1px solid #B8CFC0' }}>
              {initial}
            </div>
            <button onClick={handleLogout}
              className="text-ink-300 hover:text-danger text-xs transition-colors font-medium px-2 min-h-[44px]">
              {demoToken ? 'Exit demo' : 'Sign out'}
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex max-w-7xl mx-auto w-full px-4 py-6 gap-5">
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
        <ChatPanel />
      </div>
      {!chatOpen && (
        <button onClick={() => setChatOpen(true)} aria-label="Ask the assistant"
          className="lg:hidden fixed bottom-4 right-4 z-40 btn-primary rounded-full shadow-lg min-h-[48px] px-5">
          Ask
        </button>
      )}
    </div>
  )
}