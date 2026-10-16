import axios from 'axios'
import { useAuthStore } from '../store/authStore'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 20000,
})

api.interceptors.request.use(async (config) => {
  const demo = useAuthStore.getState().demoToken
  const user = demo ? null : (await import('./firebase')).auth.currentUser
  if (user && config.recent) await (await import('./reauth')).ensureRecentLogin(user)   // sensitive: see lib/reauth.js
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
      if (demo) useAuthStore.getState().endDemo()
      window.location.href = demo ? '/welcome' : '/login'
    } else if (status === 403 && err.response.data?.code === 'email_unverified') {
      window.dispatchEvent(new CustomEvent('vaulta:unverified'))
    } else if (status === 403 && demo) {
      // the demo is read-only: Layout shows the server's message
      window.dispatchEvent(new CustomEvent('vaulta:read-only', { detail: err.response.data?.detail }))
    }
    return Promise.reject(err)
  }
)

/** Sign in to the shared read-only demo. */
export async function startDemo() {
  const { data } = await api.post('/auth/demo', null, { timeout: 90000 })   // the very first visit builds the demo
  useAuthStore.getState().startDemo(data.token)
}

export default api
