import axios from 'axios'
import { useAuthStore } from '../store/authStore'

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
  const { APP_CHECKED, appCheckToken } = await import('./appcheck')
  // A signed-in user's request may be the one that creates their Vaulta account, which needs App Check
  if (user || APP_CHECKED.some((re) => re.test(config.url.split('?')[0]))) {
    const token = await appCheckToken()
    if (token) config.headers['X-Firebase-AppCheck'] = token
  }
  if (user) config.headers.Authorization = `Bearer ${await user.getIdToken()}`
  else if (demo) config.headers.Authorization = `Bearer ${demo}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (err) => {
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
