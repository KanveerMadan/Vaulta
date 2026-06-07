import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useEffect } from 'react'
import { onAuthStateChanged } from 'firebase/auth'
import { auth } from './lib/firebase'
import { useAuthStore } from './store/authStore'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Connect from './pages/Connect'
import Layout from './components/Layout'

function PrivateRoute() {
  const { user } = useAuthStore()
  return user ? <Outlet /> : <Navigate to="/login" replace />
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
  const { user, loading, setUser, setLoading } = useAuthStore()

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u)
      setLoading(false)
    })
    return unsub
  }, [])

  if (loading) return <Loader />

  return (
    <Routes>
      <Route path="/welcome" element={<Landing />} />
      <Route path="/login" element={!user ? <Login /> : <Navigate to="/" replace />} />
      <Route element={<PrivateRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/connect" element={<Connect />} />
        </Route>
      </Route>
      <Route path="*" element={user ? <Navigate to="/" replace /> : <Navigate to="/welcome" replace />} />
    </Routes>
  )
}