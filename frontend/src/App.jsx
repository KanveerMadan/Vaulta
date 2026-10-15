import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useEffect } from 'react'
import { onAuthStateChanged } from 'firebase/auth'
import { auth } from './lib/firebase'
import { useAuthStore } from './store/authStore'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Connect from './pages/Connect'
import Recurring from './pages/Recurring'
import People from './pages/People'
import Rules from './pages/Rules'
import Budgets from './pages/Budgets'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Cash from './pages/Cash'
import Review from './pages/Review'
import Goals from './pages/Goals'
import Onboarding from './pages/Onboarding'
import Layout from './components/Layout'

function PrivateRoute() {
  const { user, demoToken } = useAuthStore()
  return user || demoToken ? <Outlet /> : <Navigate to="/login" replace />
}

function Loader() {
  return (
    <div className="min-h-dvh bg-forest-950 flex items-center justify-center">
      <div className="flex flex-col items-center gap-5">
        <span className="font-display text-2xl font-light text-cream-200 tracking-tight">Vaulta</span>
        <div className="flex gap-1.5">
          {[0,1,2].map(i => (
            <div key={i} className="w-1.5 h-1.5 rounded-full bg-forest-300 animate-skeleton"
              style={{ animationDelay: `${i * 0.2}s` }} />
          ))}
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const { user, loading, setUser, setLoading, demoToken } = useAuthStore()
  const signedIn = user || demoToken

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u)
      setLoading(false)
    })
    return unsub
  }, [setUser, setLoading])

  if (loading) return <Loader />

  return (
    <Routes>
      <Route path="/welcome" element={<Landing />} />
      <Route path="/login" element={!user ? <Login /> : <Navigate to="/" replace />} />
      <Route element={<PrivateRoute />}>
        <Route path="/onboarding" element={<Onboarding />} />
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/connect" element={<Connect />} />
          <Route path="/recurring" element={<Recurring />} />
          <Route path="/people" element={<People />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/budgets" element={<Budgets />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/reports/:id" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/cash" element={<Cash />} />
          <Route path="/review" element={<Review />} />
          <Route path="/goals" element={<Goals />} />
        </Route>
      </Route>
      <Route path="*" element={signedIn ? <Navigate to="/" replace /> : <Navigate to="/welcome" replace />} />
    </Routes>
  )
}