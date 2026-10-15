import { create } from 'zustand'

const DEMO_KEY = 'vaulta-demo-token'
const readDemo = () => { try { return sessionStorage.getItem(DEMO_KEY) } catch { return null } }

export const useAuthStore = create((set) => ({
  user: null,
  loading: true,
  // Server-issued token for the shared read-only demo (no Firebase sign-in); kept for this tab only
  demoToken: readDemo(),
  setUser: (user) => set({ user, loading: false }),
  setLoading: (loading) => set({ loading }),
  logout: () => set({ user: null }),
  startDemo: (token) => {
    try { sessionStorage.setItem(DEMO_KEY, token) } catch { /* private mode: demo lasts until reload */ }
    set({ demoToken: token })
  },
  endDemo: () => {
    try { sessionStorage.removeItem(DEMO_KEY) } catch { /* private mode */ }
    set({ demoToken: null })
  },
}))
