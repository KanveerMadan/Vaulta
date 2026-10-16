import { initializeApp } from 'firebase/app'
import { browserLocalPersistence, browserPopupRedirectResolver, connectAuthEmulator, indexedDBLocalPersistence, initializeAuth, GoogleAuthProvider, signInWithPopup } from 'firebase/auth'

const firebaseConfig = {
  apiKey:            import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain:        import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId:         import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket:     import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId:             import.meta.env.VITE_FIREBASE_APP_ID,
}

const app = initializeApp(firebaseConfig)
// Without a popup resolver here, Auth doesn't load Google's sign-in helper (apis.google.com) for
// every visitor; it's passed only when someone actually signs in with Google.
export const auth = initializeAuth(app, { persistence: [indexedDBLocalPersistence, browserLocalPersistence] })
export const googleProvider = new GoogleAuthProvider()
// Browser tests sign in against the local Firebase Auth emulator (e2e/README.md)
if (import.meta.env.VITE_FIREBASE_AUTH_EMULATOR) {
  connectAuthEmulator(auth, import.meta.env.VITE_FIREBASE_AUTH_EMULATOR, { disableWarnings: true })
}

/** Google sign-in popup: the only place Google's own sign-in scripts are loaded. */
export const signInWithGoogle = () => signInWithPopup(auth, googleProvider, browserPopupRedirectResolver)
