import { Suspense, useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useApi } from '../lib/format'
import { signOut } from 'firebase/auth'
import { auth } from '../lib/firebase'
import { useAuthStore } from '../store/authStore'
import ChatPanel from './ChatPanel'
import AlertsBell from './AlertsBell'
import { useFinanceStore } from '../store/financeStore'
import { ChartPieSlice, ChatCircleText, Flag, GearSix, House, List, ListBullets, MagnifyingGlass, Money, Newspaper, Plugs, Repeat, SignOut, SlidersHorizontal, Question, Users, X } from '@phosphor-icons/react'
import ThemeSwitch from '../ui/ThemeSwitch'
import Wordmark from '../ui/Wordmark'
import { useMedia } from '../lib/useMedia'
import { useCommandPalette } from '../lib/commands'
import CommandPalette from './CommandPalette'

const NAV = [
  { to: '/', label: 'Home', end: true, icon: House },
  { to: '/transactions', label: 'Transactions', icon: ListBullets },
  { to: '/budgets', label: 'Budgets', icon: ChartPieSlice },
  { to: '/goals', label: 'Goals', icon: Flag },
  { to: '/cash', label: 'Cash', icon: Money },
  { to: '/recurring', label: 'Recurring', icon: Repeat },
  { to: '/reports', label: 'Reports', icon: Newspaper },
  { to: '/people', label: 'People', icon: Users },
  { to: '/rules', label: 'Rules', icon: SlidersHorizontal },
  { to: '/connect', label: 'Connect', icon: Plugs },
  { to: '/settings', label: 'Settings', icon: GearSix },
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

  // "?": replay the guided tour on the home page (components/GuidedTour.jsx); there's no tour in the demo
  const tourButton = (size) => demoToken ? null : (
    <button onClick={() => navigate('/', { state: { tour: Date.now() } })} aria-label="Take the tour" title="Take the tour"
      data-tour="help" className={`${size} flex items-center justify-center rounded-sm text-ink-2 hover:bg-sunken`}>
      <Question size={19} aria-hidden />
    </button>
  )

  // On purpose: PrivateRoute sends a leaving user to the landing page (an ended session would go to /login)
  const handleLogout = async () => {
    useAuthStore.getState().setLeaving(true)
    navigate('/welcome')
    if (demoToken) endDemo()
    else await signOut(auth)
    logout()
  }
  const signUp = () => { endDemo(); navigate('/login') }

  // First login: start setup (skippable; Settings → Resume setup brings it back)
  const { data: onboarding } = useApi('/api/onboarding', 0)
  useEffect(() => {
    if (onboarding?.status === 'new') navigate('/onboarding', { replace: true })
  }, [onboarding, navigate])

  const openPalette = useCommandPalette((st) => st.open)
  const desktop = useMedia('(min-width: 1024px)')   // render one shell, so the bell polls once
  const who = demoToken ? 'Demo account' : user?.displayName || user?.email

  const navList = (
    <ul className="flex flex-col gap-0.5">
      {NAV.map(({ to, label, end, icon: Icon }) => (
        <li key={to}>
          <NavLink to={to} end={end} onClick={() => setMenuOpen(false)}
            className={({ isActive }) => `flex items-center gap-3 rounded-sm px-3 py-2 text-sm font-medium transition-colors duration-fast
              ${isActive ? 'bg-accent-tint text-accent-text' : 'text-ink-2 hover:bg-sunken hover:text-ink'}`}>
            <Icon size={18} aria-hidden />{label}
          </NavLink>
        </li>
      ))}
    </ul>
  )

  return (
    <div className="min-h-dvh bg-canvas">
      <a href="#main" className="sr-only-focusable fixed left-3 top-3 z-[80] btn-primary">Skip to content</a>
      {demoToken && (
        <div role="note" className="bg-warn-tint text-ink text-sm px-4 py-2 text-center border-b border-line">
          You're viewing a demo with sample data.{' '}
          <NavLink to="/try" className="font-semibold underline underline-offset-2">Try the simulations</NavLink>{' '}or{' '}
          <button onClick={signUp} className="font-semibold underline underline-offset-2">sign up to track your own.</button>
        </div>
      )}
      {readOnly && (
        <div role="alert" className="fixed bottom-safe-20 lg:bottom-6 left-1/2 -translate-x-1/2 z-[75] bg-inverse text-on-inverse text-sm rounded-md shadow-3 px-4 py-3 max-w-[calc(100vw-2rem)] animate-rise">
          {readOnly}
        </div>
      )}

      {/* Phones and tablets: top bar with a menu */}
      {!desktop && <header className="lg:hidden sticky top-0 z-30 bg-surface/95 backdrop-blur border-b border-line standalone-safe-top">
        <div className="h-14 px-3 flex items-center gap-1">
          <button onClick={() => setMenuOpen((v) => !v)} aria-expanded={menuOpen} aria-controls="main-nav"
            className="w-11 h-11 flex items-center justify-center rounded-sm text-ink hover:bg-sunken" aria-label="Menu">
            {menuOpen ? <X size={20} /> : <List size={20} />}
          </button>
          <Wordmark className="ml-1" />
          <div className="ml-auto flex items-center gap-1">
            <button onClick={openPalette} aria-label="Search and commands" className="w-11 h-11 flex items-center justify-center rounded-sm text-ink-2 hover:bg-sunken"><MagnifyingGlass size={19} /></button>
            {tourButton('w-11 h-11')}
            <AlertsBell />
          </div>
        </div>
        <nav id="main-nav" aria-label="Main" className={`${menuOpen ? 'block' : 'hidden'} border-t border-line px-3 pt-3 pb-safe-3 max-h-[calc(100dvh-3.5rem)] overflow-y-auto`}>
          {navList}
          <div className="mt-3 pt-3 border-t border-line flex items-center justify-between gap-2">
            <ThemeSwitch compact />
            <button onClick={handleLogout} className="btn-quiet text-sm">{demoToken ? 'Exit demo' : 'Sign out'}</button>
          </div>
        </nav>
      </header>}

      <div className="lg:grid lg:grid-cols-[232px_minmax(0,1fr)] xl:grid-cols-[232px_minmax(0,1fr)_320px]">
        {/* Desktop: sidebar */}
        {desktop && <aside className="hidden lg:flex flex-col sticky top-0 h-dvh border-r border-line bg-surface px-3 py-4">
          <div className="flex items-center justify-between px-2 mb-4">
            <Wordmark />
            <div className="flex items-center">{tourButton('w-9 h-9')}<AlertsBell /></div>
          </div>
          <button onClick={openPalette} className="mb-4 flex items-center gap-2 rounded-sm border border-line bg-canvas px-3 h-9 text-sm text-muted hover:border-line-strong">
            <MagnifyingGlass size={16} aria-hidden /><span className="flex-1 text-left">Search or jump to</span><kbd className="kbd">⌘K</kbd>
          </button>
          <nav aria-label="Main" className="flex-1 overflow-y-auto">{navList}</nav>
          <div className="pt-3 mt-3 border-t border-line space-y-3">
            <ThemeSwitch compact />
            <div className="flex items-center gap-2 px-1">
              <span className="flex-1 truncate text-micro text-muted" title={who}>{who}</span>
              <button onClick={handleLogout} className="btn-quiet h-8 text-micro"><SignOut size={14} aria-hidden />{demoToken ? 'Exit demo' : 'Sign out'}</button>
            </div>
          </div>
        </aside>}

        {/* below xl the floating Ask button sits over the bottom of the page: leave room to scroll past it */}
        <main id="main" tabIndex={-1} className="min-w-0 px-4 sm:px-6 pt-6 pb-28 xl:pb-6 outline-none">
          <Suspense fallback={<div className="space-y-4 max-w-5xl mx-auto" aria-label="Loading"><div className="skeleton h-10 w-56" /><div className="skeleton h-4 w-full" /><div className="skeleton h-4 w-4/5" /></div>}>
            <Outlet />
          </Suspense>
        </main>
        <ChatPanel />
      </div>
      <CommandPalette />
      {/* hidden while the phone menu is open: on tall phones it would sit over the menu's last items */}
      {!chatOpen && !menuOpen && (
        <button onClick={() => setChatOpen(true)} aria-label="Ask the assistant"
          className="xl:hidden fixed bottom-safe-4 right-4 z-40 btn-primary rounded-full shadow-3 h-12 px-5">
          <ChatCircleText size={18} aria-hidden /> Ask
        </button>
      )}
    </div>
  )
}
