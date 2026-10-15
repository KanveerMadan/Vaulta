import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { lazy, Suspense, useEffect } from 'react'
import { onAuthStateChanged } from 'firebase/auth'
import { auth } from './lib/firebase'
import { useAuthStore } from './store/authStore'
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
import Security from './pages/Security'
import Layout from './components/Layout'
import { Toaster } from './ui/Toast'

// Showpieces load on their own (and bring the animation library with them); the workspace never does
const Landing = lazy(() => import('./pages/landing/Landing'))

function PrivateRoute() {
  const { user, demoToken } = useAuthStore()
  return user || demoToken ? <Outlet /> : <Navigate to="/welcome" replace />
}

function Loader() {
  return (
    <div className="min-h-dvh bg-canvas flex items-center justify-center" role="status" aria-label="Loading Vaulta">
      <div className="flex flex-col items-center gap-4">
        <span className="font-display text-2xl font-semibold tracking-tight text-ink">Vaulta</span>
        <span className="block w-24 h-px bg-line overflow-hidden"><span className="block h-px w-1/3 bg-accent animate-pulse" /></span>
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
    <>
    <Toaster />
    <Routes>
      <Route path="/welcome" element={<Suspense fallback={<Loader />}><Landing /></Suspense>} />
      <Route path="/security" element={<Security />} />
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
    </>
  )
}