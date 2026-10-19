import axios from 'axios'
import { useAuthStore } from '../store/authStore'
import { canResend, isColdError, wake } from './wake'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 20000,
})

// Requests still in flight when the page is left are cancelled cleanly, instead of being cut off by the navigation
// (WebKit reports a cut-off request as an error from the page being left). The callers' catch blocks see a cancel.
let leaving = new AbortController()
if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => leaving.abort())
  window.addEventListener('pageshow', (e) => { if (e.persisted) leaving = new AbortController() })   // back/forward cache
}

api.interceptors.request.use(async (config) => {
  if (!config.signal) config.signal = leaving.signal
  const demo = useAuthStore.getState().demoToken
  const user = demo ? null : (await import('./firebase')).auth.currentUser
  if (user && config.recent) await (await import('./reauth')).ensureRecentLogin(user)   // sensitive: see lib/reauth.js
  // reCAPTCHA on the routes bots would abuse, and while a signed-in user's account may still be created (lib/recaptcha.js)
  const { HEADER, actionFor, accountKnown, recaptchaToken } = await import('./recaptcha')
  const action = actionFor(config.url.split('?')[0], { signedIn: !!user, accountKnown: !!user && accountKnown(user.uid) })
  if (action) {
    const token = await recaptchaToken(action)
    if (token) config.headers[HEADER] = token
  }
  if (user) config.headers.Authorization = `Bearer ${await user.getIdToken()}`
  else if (demo) config.headers.Authorization = `Bearer ${demo}`
  return config
})

api.interceptors.response.use(
  async (res) => {
    // the API answered a signed-in request: the account exists, so no more 'signup' tokens for it
    const uid = res.config.headers?.Authorization && !useAuthStore.getState().demoToken
      ? (await import('./firebase')).auth.currentUser?.uid : null
    if (uid) (await import('./recaptcha')).rememberAccount(uid)
    return res
  },
  async (err) => {
    // a sleeping API (lib/wake.js): wait for it, then send again where that's safe
    if (err.config && !err.config._woke && isColdError(err)) {
      if (await wake(api.defaults.baseURL) && canResend(err.config, err)) {
        err.config._woke = true
        return api(err.config)
      }
      return Promise.reject(err)
    }
    const status = err.response?.status
    if (err.response?.data instanceof Blob && err.response.data.type.includes('json')) {
      err.response.data = JSON.parse(await err.response.data.text())     // blob requests (export) get JSON errors
    }
    if (status === 403 && err.response.data?.code === 'reauth_required' && !err.config._reauthed) {
      const { requestReauth } = await import('./reauth')
      await requestReauth()                        // rejects if the user cancels: the original error stands
        .then(() => { err.config._reauthed = true }, () => {})
      if (err.config._reauthed) return api(err.config)
      return Promise.reject(err)
    }
    const demo = useAuthStore.getState().demoToken
    if (status === 401) {
      if (demo) {
        useAuthStore.getState().endDemo()
        window.location.href = '/welcome'
      } else {
        await signOutLocally(err.response.data?.detail)
      }
    } else if (status === 403 && err.response.data?.code === 'email_unverified') {
      window.dispatchEvent(new CustomEvent('vaulta:unverified'))
    } else if (status === 403 && demo) {
      // the demo is read-only: Layout shows the server's message
      window.dispatchEvent(new CustomEvent('vaulta:read-only', { detail: err.response.data?.detail }))
    }
    return Promise.reject(err)
  }
)

let signingOut = null
/**
 * The session ended (expired, revoked by "sign out of all devices", account disabled): forget it in this browser
 * once, however many requests failed. PrivateRoute then sends the user to the login page and back here afterwards.
 */
function signOutLocally(detail) {
  signingOut ??= (async () => {
    const [{ signOut }, { auth }] = await Promise.all([import('firebase/auth'), import('./firebase')])
    // The login page shows why; App's routes send the signed-out user there and back to this page afterwards
    useAuthStore.getState().setSignedOutNotice(detail || 'Your session ended. Sign in again.')
    await signOut(auth).catch(() => {})
  })().finally(() => { signingOut = null })
  return signingOut
}

/** Sign in to the shared read-only demo. */
export async function startDemo() {
  const { data } = await api.post('/auth/demo', null, { timeout: 90000 })   // the very first visit builds the demo
  useAuthStore.getState().startDemo(data.token)
}

export default api
