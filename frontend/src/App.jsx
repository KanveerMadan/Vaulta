import { Routes, Route, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { lazy, Suspense, useEffect } from 'react'
import { useAuthStore } from './store/authStore'
import { Toaster } from './ui/Toast'
import ReauthDialog from './components/ReauthDialog'
import { applyPageMeta } from './lib/pageMeta'
import Landing from './pages/landing/Landing'   // in the main bundle: the first thing most visitors see

// Every other page is its own chunk. Showpieces (the landing's story, onboarding, Wrapped) bring the animation
// library with them; the workspace never loads it. Firebase loads off the landing's critical path.
const Security = lazy(() => import('./pages/Security'))
const Privacy = lazy(() => import('./pages/Privacy'))
const Login = lazy(() => import('./pages/Login'))
const VerifyEmail = lazy(() => import('./pages/VerifyEmail'))
const Onboarding = lazy(() => import('./pages/Onboarding'))
const Wrapped = lazy(() => import('./pages/wrapped/Wrapped'))
const Layout = lazy(() => import('./components/Layout'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Transactions = lazy(() => import('./pages/Transactions'))
const Connect = lazy(() => import('./pages/Connect'))
const Try = lazy(() => import('./pages/Try'))
const Recurring = lazy(() => import('./pages/Recurring'))
const People = lazy(() => import('./pages/People'))
const Rules = lazy(() => import('./pages/Rules'))
const Budgets = lazy(() => import('./pages/Budgets'))
const Reports = lazy(() => import('./pages/Reports'))
const Settings = lazy(() => import('./pages/Settings'))
const Cash = lazy(() => import('./pages/Cash'))
const Review = lazy(() => import('./pages/Review'))
const Goals = lazy(() => import('./pages/Goals'))

// The app shell and home download while Firebase restores the session, not after it
// A prefetch: if it fails (offline, or cancelled by leaving the page) the routes load the chunks themselves
const loadShell = () => Promise.all([import('./components/Layout'), import('./pages/Dashboard')]).catch(() => {})

// Pages an unconfirmed email/password account may open (the API refuses everything else with email_unverified)
const UNVERIFIED_PAGES = ['/onboarding', '/settings']

function PrivateRoute() {
  const { user, verified, demoToken, loading, leaving } = useAuthStore()
  const { pathname } = useLocation()
  useEffect(() => { loadShell() }, [])
  if (user && !verified && !demoToken && !UNVERIFIED_PAGES.includes(pathname)) {
    return <Navigate to="/verify-email" replace state={{ next: pathname }} />
  }
  if (demoToken || user) return <Outlet />
  if (loading) return <Loader />
  // Signed out on a page inside the app: log in and come back to it. The bare root is the landing page.
  return pathname === '/' || leaving ? <Navigate to="/welcome" replace /> : <Navigate to="/login" replace state={{ next: pathname }} />
}

// Signed in on /login: go where the user was heading (state.next), else home
function AfterLogin() {
  const { state } = useLocation()
  const next = typeof state?.next === 'string' && state.next.startsWith('/') && !state.next.startsWith('//') ? state.next : '/'
  return <Navigate to={next} replace />
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
    let unsub = () => {}
    let alive = true
    Promise.all([import('firebase/auth'), import('./lib/firebase')]).then(([{ onAuthStateChanged }, { auth }]) => {
      if (!alive) return
      unsub = onAuthStateChanged(auth, (u) => { setUser(u); setLoading(false) })
    })
    return () => { alive = false; unsub() }
  }, [setUser, setLoading])

  const { pathname } = useLocation()
  useEffect(() => applyPageMeta(pathname), [pathname])

  // The API said this account must confirm its email first (403 email_unverified): show the check-your-inbox screen
  const navigate = useNavigate()
  useEffect(() => {
    const onUnverified = () => navigate('/verify-email')
    window.addEventListener('vaulta:unverified', onUnverified)
    return () => window.removeEventListener('vaulta:unverified', onUnverified)
  }, [navigate])

  const page = (el) => <Suspense fallback={<Loader />}>{el}</Suspense>
  return (
    <>
    <Toaster />
    {user && <ReauthDialog />}
    <Routes>
      <Route path="/welcome" element={<Landing />} />
      <Route path="/security" element={page(<Security />)} />
      <Route path="/privacy" element={page(<Privacy />)} />
      <Route path="/verify-email" element={loading ? <Loader /> : page(<VerifyEmail />)} />
      <Route path="/login" element={loading ? <Loader /> : !user ? page(<Login />) : <AfterLogin />} />
      <Route element={<PrivateRoute />}>
        <Route path="/onboarding" element={page(<Onboarding />)} />
        <Route path="/reports/:id/wrapped" element={page(<Wrapped />)} />
        <Route element={page(<Layout />)}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/connect" element={<Connect />} />
          <Route path="/try" element={<Try />} />
          <Route path="/recurring" element={<Recurring />} />
          <Route path="/people" element={<People />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/budgets" element={<Budgets />} />
          <Route path="/goals" element={<Goals />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/reports/:id" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/cash" element={<Cash />} />
          <Route path="/review" element={<Review />} />
        </Route>
      </Route>
      <Route path="*" element={loading && !demoToken ? <Loader /> : signedIn ? <Navigate to="/" replace /> : <Navigate to="/welcome" replace />} />
    </Routes>
    </>
  )
}
