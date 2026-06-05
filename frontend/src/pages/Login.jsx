import { useState } from 'react'
import { signInWithPopup, signInWithEmailAndPassword, createUserWithEmailAndPassword } from 'firebase/auth'
import { auth, googleProvider } from '../lib/firebase'
import { useAuthStore } from '../store/authStore'
import { useNavigate } from 'react-router-dom'

export default function Login() {
  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { setUser } = useAuthStore()
  const navigate = useNavigate()

  const handleGoogle = async () => {
    setError(''); setLoading(true)
    try {
      const result = await signInWithPopup(auth, googleProvider)
      setUser(result.user)
      navigate('/')
    } catch (e) {
      setError('Google sign-in failed. Try again.')
    } finally { setLoading(false) }
  }

  const handleEmail = async (e) => {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const fn = mode === 'login' ? signInWithEmailAndPassword : createUserWithEmailAndPassword
      const result = await fn(auth, email, password)
      setUser(result.user)
      navigate('/')
    } catch (e) {
      const msgs = {
        'auth/invalid-credential': 'Wrong email or password.',
        'auth/email-already-in-use': 'Account already exists. Log in instead.',
        'auth/weak-password': 'Password must be at least 6 characters.',
        'auth/invalid-email': 'Enter a valid email.',
      }
      setError(msgs[e.code] || 'Something went wrong.')
    } finally { setLoading(false) }
  }

  return (
    <div className="min-h-dvh bg-bg flex items-center justify-center p-4">
      {/* Background glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[500px] rounded-full bg-brand opacity-[0.04] blur-[120px]" />
      </div>

      <div className="w-full max-w-sm animate-fade-up">
        {/* Logo */}
        <div className="flex flex-col items-center mb-10">
          <div className="w-12 h-12 rounded-2xl bg-brand flex items-center justify-center mb-4 shadow-lg shadow-brand/20">
            <span className="text-white font-bold text-xl">V</span>
          </div>
          <h1 className="text-2xl font-semibold text-t1 tracking-tight">Vaulta</h1>
          <p className="text-t3 text-sm mt-1">Personal Finance AI for India</p>
        </div>

        {/* Card */}
        <div className="bg-card border border-border rounded-2xl p-6">
          {/* Toggle */}
          <div className="flex bg-elevated rounded-xl p-1 mb-6">
            {['login', 'signup'].map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setError('') }}
                className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  mode === m ? 'bg-brand text-white shadow-sm' : 'text-t2 hover:text-t1'
                }`}
              >
                {m === 'login' ? 'Log in' : 'Sign up'}
              </button>
            ))}
          </div>

          {/* Google */}
          <button
            onClick={handleGoogle}
            disabled={loading}
            className="w-full flex items-center justify-center gap-3 bg-elevated hover:bg-border border border-border rounded-xl py-3 text-t1 text-sm font-medium transition-all duration-200 mb-4 disabled:opacity-50"
          >
            <GoogleIcon />
            Continue with Google
          </button>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 h-px bg-border" />
            <span className="text-t3 text-xs">or</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          {/* Email form */}
          <form onSubmit={handleEmail} className="space-y-3">
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full bg-elevated border border-border rounded-xl px-4 py-3 text-t1 text-sm placeholder-t3 focus:outline-none focus:border-brand transition-colors"
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full bg-elevated border border-border rounded-xl px-4 py-3 text-t1 text-sm placeholder-t3 focus:outline-none focus:border-brand transition-colors"
            />
            {error && <p className="text-negative text-xs">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-brand hover:bg-brand-light text-white font-medium py-3 rounded-xl transition-all duration-200 text-sm disabled:opacity-50 active:scale-[0.98]"
            >
              {loading ? 'Please wait...' : mode === 'login' ? 'Log in' : 'Create account'}
            </button>
          </form>
        </div>

        <p className="text-center text-t3 text-xs mt-6">
          Flat ₹99/month when we charge. No data selling. Ever.
        </p>
      </div>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
    </svg>
  )
}