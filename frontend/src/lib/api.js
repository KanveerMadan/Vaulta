import axios from 'axios'
import { useAuthStore } from '../store/authStore'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 20000,
})

api.interceptors.request.use(async (config) => {
  const { getAuth } = await import('firebase/auth')
  const user = getAuth().currentUser
  const demo = useAuthStore.getState().demoToken
  if (user) config.headers.Authorization = `Bearer ${await user.getIdToken()}`
  else if (demo) config.headers.Authorization = `Bearer ${demo}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status
    const demo = useAuthStore.getState().demoToken
    if (status === 401) {
      if (demo) useAuthStore.getState().endDemo()
      window.location.href = demo ? '/welcome' : '/login'
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
