import { useState } from 'react'
import { signInWithPopup, signInWithEmailAndPassword, createUserWithEmailAndPassword } from 'firebase/auth'
import { auth, googleProvider } from '../lib/firebase'
import { useAuthStore } from '../store/authStore'
import { useNavigate } from 'react-router-dom'

const ERROR_MAP = {
  'auth/invalid-credential':    'Incorrect email or password.',
  'auth/email-already-in-use':  'An account with this email already exists.',
  'auth/weak-password':         'Password must be at least 6 characters.',
  'auth/invalid-email':         'Please enter a valid email address.',
  'auth/too-many-requests':     'Too many attempts. Try again in a few minutes.',
  'auth/popup-closed-by-user':  null,
}

export default function Login() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { setUser } = useAuthStore()
  const navigate = useNavigate()

  const onSuccess = (user) => { setUser(user); navigate('/') }

  const handleGoogle = async () => {
    setError(''); setLoading(true)
    try {
      const r = await signInWithPopup(auth, googleProvider)
      onSuccess(r.user)
    } catch (e) {
      const msg = ERROR_MAP[e.code]
      if (msg !== null) setError(msg || 'Google sign-in failed. Please try again.')
    } finally { setLoading(false) }
  }

  const handleEmail = async (e) => {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const fn = mode === 'login' ? signInWithEmailAndPassword : createUserWithEmailAndPassword
      const r = await fn(auth, email, password)
      onSuccess(r.user)
    } catch (e) {
      setError(ERROR_MAP[e.code] || 'Something went wrong. Please try again.')
    } finally { setLoading(false) }
  }

  return (
    <div className="min-h-dvh bg-forest-950 flex">
      {/* Left panel — brand */}
      <div className="hidden lg:flex flex-col justify-between w-[480px] shrink-0 bg-forest-900 border-r border-forest-700 p-12">
        <div>
          <span className="font-display text-2xl font-light text-cream-200 tracking-tight">Vaulta</span>
        </div>
        <div className="space-y-8">
          <div>
            <p className="font-display text-4xl font-light text-cream-100 leading-tight">
              Your money,<br />finally makes sense.
            </p>
            <p className="mt-4 text-forest-200 text-sm leading-relaxed max-w-xs">
              AI that reads your Gmail, bank SMS, and UPI history to give you an honest picture of where your money goes.
            </p>
          </div>
          <div className="space-y-3">
            {[
              'Works with any Indian bank or UPI app',
              'No loan upselling. No hidden agenda.',
              'Ask in English or Hinglish',
            ].map((t) => (
              <div key={t} className="flex items-center gap-3">
                <div className="w-1.5 h-1.5 rounded-full bg-forest-300 shrink-0" />
                <span className="text-forest-100 text-sm">{t}</span>
              </div>
            ))}
          </div>
        </div>
        <p className="text-forest-500 text-xs">
          ₹99/month when we charge. We make money when you pay us, not when we sell your data.
        </p>
      </div>

      {/* Right panel — form */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-sm animate-fade-up">
          {/* Mobile logo */}
          <div className="lg:hidden mb-10 text-center">
            <span className="font-display text-2xl font-light text-cream-200">Vaulta</span>
            <p className="text-forest-300 text-sm mt-1">Personal Finance AI for India</p>
          </div>

          <div className="mb-8">
            <h1 className="text-xl font-semibold text-cream-100">
              {mode === 'login' ? 'Welcome back' : 'Create your account'}
            </h1>
            <p className="text-forest-300 text-sm mt-1">
              {mode === 'login'
                ? "Don't have an account? "
                : 'Already have an account? '}
              <button
                onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError('') }}
                className="text-cream-300 hover:text-cream-100 underline underline-offset-2 transition-colors"
              >
                {mode === 'login' ? 'Sign up' : 'Log in'}
              </button>
            </p>
          </div>

          <div className="space-y-3">
            {/* Google */}
            <button
              onClick={handleGoogle}
              disabled={loading}
              className="w-full flex items-center justify-center gap-3 bg-forest-800 hover:bg-forest-700
                         border border-forest-600 hover:border-forest-500 text-cream-200 text-sm font-medium
                         py-3 rounded-lg transition-all duration-150 disabled:opacity-40 active:scale-[0.98]"
            >
              <GoogleIcon />
              Continue with Google
            </button>

            <div className="flex items-center gap-3">
              <div className="flex-1 h-px bg-forest-700" />
              <span className="text-forest-500 text-xs">or</span>
              <div className="flex-1 h-px bg-forest-700" />
            </div>

            {/* Email form */}
            <form onSubmit={handleEmail} className="space-y-3">
              <div>
                <label className="label block mb-1.5">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  className="input"
                  autoComplete="email"
                />
              </div>
              <div>
                <label className="label block mb-1.5">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="input"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                />
              </div>

              {error && (
                <div className="bg-danger/10 border border-danger/20 rounded-lg px-3 py-2.5">
                  <p className="text-danger text-xs">{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !email || !password}
                className="btn-primary w-full mt-1"
              >
                {loading
                  ? 'Please wait...'
                  : mode === 'login' ? 'Log in' : 'Create account'}
              </button>
            </form>
          </div>

          <p className="text-center text-forest-500 text-xs mt-8 leading-relaxed">
            By continuing, you agree to our terms of service.<br />
            Your data is never sold or shared.
          </p>
        </div>
      </div>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" fill="none">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
    </svg>
  )
}