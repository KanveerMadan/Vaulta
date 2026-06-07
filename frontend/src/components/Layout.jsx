import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { signOut } from 'firebase/auth'
import { auth } from '../lib/firebase'
import { useAuthStore } from '../store/authStore'
import ChatPanel from './ChatPanel'

export default function Layout() {
  const { logout, user } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await signOut(auth)
    logout()
    navigate('/welcome')
  }

  const initial = (user?.displayName?.[0] || user?.email?.[0] || 'U').toUpperCase()

  return (
    <div className="min-h-dvh flex flex-col" style={{ background: '#F2F7F3' }}>
      {/* Header */}
      <header className="sticky top-0 z-30 bg-white border-b border-sage-200"
        style={{ boxShadow: '0 1px 3px rgba(45,106,79,0.06)' }}>
        <div className="max-w-7xl mx-auto px-5 h-14 flex items-center gap-4">
          <span className="font-display text-lg font-light tracking-tight mr-3"
            style={{ color: '#1A2E1E' }}>
            Vaulta
          </span>

          <nav className="flex items-center gap-1">
            {[{ to: '/', label: 'Dashboard', end: true }, { to: '/connect', label: 'Connect' }].map(({ to, label, end }) => (
              <NavLink key={to} to={to} end={end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm transition-all duration-150 font-medium ${
                    isActive
                      ? 'text-safe'
                      : 'text-ink-500 hover:text-ink-700 hover:bg-sage-100'
                  }`
                }
                style={({ isActive }) => isActive ? {
                  background: '#E8F5EB',
                  color: '#2D6A4F',
                } : {}}
              >
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="text-ink-300 text-xs hidden sm:block truncate max-w-[160px]">
              {user?.displayName || user?.email}
            </span>
            <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-semibold"
              style={{ background: '#E8F5EB', color: '#2D6A4F', border: '1px solid #B8CFC0' }}>
              {initial}
            </div>
            <button onClick={handleLogout}
              className="text-ink-300 hover:text-danger text-xs transition-colors font-medium">
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex max-w-7xl mx-auto w-full px-5 py-6 gap-5">
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
        <ChatPanel />
      </div>
    </div>
  )
}