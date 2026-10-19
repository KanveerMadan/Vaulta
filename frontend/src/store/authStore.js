import { create } from 'zustand'

const DEMO_KEY = 'vaulta-demo-token'
const readDemo = () => { try { return sessionStorage.getItem(DEMO_KEY) } catch { return null } }

// Google sign-ins count as verified; email/password accounts must confirm their address (the API enforces it too)
export const isVerified = (user) => !!user && (user.emailVerified || user.providerData?.some((p) => p.providerId === 'google.com'))

export const useAuthStore = create((set) => ({
  user: null,
  verified: false,
  loading: true,
  // Server-issued token for the shared read-only demo (no Firebase sign-in); kept for this tab only
  demoToken: readDemo(),
  setUser: (user) => set((s) => ({ user, verified: isVerified(user), loading: false, leaving: user ? false : s.leaving })),
  // Signing out or exiting the demo on purpose: PrivateRoute sends the user to the landing page, not to /login
  leaving: false,
  setLeaving: (leaving) => set({ leaving }),
  // after user.reload(): Firebase updates the same object, so re-read the flag
  refreshVerified: () => set((s) => ({ verified: isVerified(s.user) })),
  setLoading: (loading) => set({ loading }),
  logout: () => set({ user: null, verified: false }),
  // Why the session ended (shown once on the login page): revoked, expired, disabled
  signedOutNotice: null,
  setSignedOutNotice: (signedOutNotice) => set({ signedOutNotice }),
  startDemo: (token) => {
    try { sessionStorage.setItem(DEMO_KEY, token) } catch { /* private mode: demo lasts until reload */ }
    set({ demoToken: token, leaving: false })
  },
  endDemo: () => {
    try { sessionStorage.removeItem(DEMO_KEY) } catch { /* private mode */ }
    set({ demoToken: null })
  },
}))
