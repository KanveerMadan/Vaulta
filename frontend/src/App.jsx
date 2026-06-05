import { Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { useEffect } from 'react'
import { onAuthStateChanged } from 'firebase/auth'
import { auth } from './lib/firebase'
import { useAuthStore } from './store/authStore'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Connect from './pages/Connect'
import Layout from './components/Layout'

function PrivateRoute() {
  const { user } = useAuthStore()
  return user ? <Outlet /> : <Navigate to="/login" replace />
}

function FullScreenLoader() {
  return (
    <div className="min-h-dvh bg-bg flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 rounded-2xl bg-brand flex items-center justify-center">
          <span className="text-white font-bold text-lg">V</span>
        </div>
        <div className="w-5 h-5 border-2 border-brand border-t-transparent rounded-full animate-spin" />
      </div>
    </div>
  )
}

export default function App() {
  const { user, loading, setUser, setLoading } = useAuthStore()

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser)
      setLoading(false)
    })
    return unsub
  }, [])

  if (loading) return <FullScreenLoader />

  return (
    <Routes>
      <Route path="/login" element={!user ? <Login /> : <Navigate to="/" replace />} />
      <Route element={<PrivateRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/connect" element={<Connect />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}