import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 15000,
})

// Attach Firebase token to every request
api.interceptors.request.use(async (config) => {
  try {
    const { getAuth } = await import('firebase/auth')
    const auth = getAuth()
    if (auth.currentUser) {
      const token = await auth.currentUser.getIdToken()
      config.headers.Authorization = `Bearer ${token}`
    }
  } catch (_) {}
  return config
})

// Auto-logout on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api