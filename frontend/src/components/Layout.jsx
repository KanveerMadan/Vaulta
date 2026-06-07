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
    navigate('/login')
  }

  const initial = user?.displayName?.[0] || user?.email?.[0] || 'U'

  return (
    <div className="min-h-dvh bg-forest-950 flex flex-col">
      <header className="sticky top-0 z-30 border-b border-forest-800 bg-forest-950/90 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-5 h-14 flex items-center gap-6">
          <span className="font-display text-lg font-light text-cream-200 tracking-tight mr-2">Vaulta</span>

          <nav className="flex items-center gap-1">
            {[
              { to: '/', label: 'Dashboard', end: true },
              { to: '/connect', label: 'Connect' },
            ].map(({ to, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm transition-all duration-150 ${
                    isActive
                      ? 'bg-forest-800 text-cream-200 font-medium'
                      : 'text-forest-300 hover:text-cream-200 hover:bg-forest-800/50'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <span className="text-forest-400 text-xs hidden sm:block truncate max-w-[160px]">
              {user?.displayName || user?.email}
            </span>
            <div className="w-7 h-7 rounded-full bg-forest-700 border border-forest-500 flex items-center justify-center">
              <span className="text-cream-300 text-xs font-medium uppercase">{initial}</span>
            </div>
            <button
              onClick={handleLogout}
              className="text-forest-400 hover:text-danger text-xs transition-colors ml-1"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 flex max-w-7xl mx-auto w-full px-5 py-6 gap-5">
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
        <ChatPanel />
      </div>
    </div>
  )
}