import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { signOut } from 'firebase/auth'
import { auth } from '../lib/firebase'
import { useAuthStore } from '../store/authStore'
import { LayoutDashboard, Plug, LogOut } from 'lucide-react'
import ChatPanel from './ChatPanel'

export default function Layout() {
  const { logout, user } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await signOut(auth)
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-dvh bg-bg flex flex-col">
      {/* Top nav */}
      <header className="border-b border-border bg-bg/80 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-brand flex items-center justify-center">
              <span className="text-white font-bold text-xs">V</span>
            </div>
            <span className="font-semibold text-t1 text-sm">Vaulta</span>
          </div>

          <nav className="flex items-center gap-1">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  isActive ? 'bg-brand-dim text-brand' : 'text-t2 hover:text-t1 hover:bg-elevated'
                }`
              }
            >
              <LayoutDashboard size={14} /> Dashboard
            </NavLink>
            <NavLink
              to="/connect"
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  isActive ? 'bg-brand-dim text-brand' : 'text-t2 hover:text-t1 hover:bg-elevated'
                }`
              }
            >
              <Plug size={14} /> Connect
            </NavLink>
          </nav>

          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 text-t3 hover:text-negative text-xs transition-colors"
          >
            <LogOut size={14} /> Logout
          </button>
        </div>
      </header>

      {/* Main + Chat side by side */}
      <div className="flex-1 flex max-w-6xl mx-auto w-full px-4 py-6 gap-6">
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
        <ChatPanel />
      </div>
    </div>
  )
}