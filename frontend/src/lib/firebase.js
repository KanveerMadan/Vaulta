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

export const app = initializeApp(firebaseConfig)
// Without a popup resolver here, Auth doesn't load Google's sign-in helper (apis.google.com) for
// every visitor; it's passed only when someone actually signs in with Google.
export const auth = initializeAuth(app, { persistence: [indexedDBLocalPersistence, browserLocalPersistence] })
export const googleProvider = new GoogleAuthProvider()
// Browser tests sign in against the local Firebase Auth emulator (e2e/README.md)
if (import.meta.env.VITE_FIREBASE_AUTH_EMULATOR) {
  connectAuthEmulator(auth, import.meta.env.VITE_FIREBASE_AUTH_EMULATOR, { disableWarnings: true })
}

// Browser tests only (vite --mode e2e; the block is removed from every other build): sign in with a Google
// credential the emulator accepts, because its popup never reports back inside Playwright's browser
if (import.meta.env.MODE === 'e2e') {
  window.__e2eGoogleSignIn = async (email) => {
    const { GoogleAuthProvider, signInWithCredential } = await import('firebase/auth')
    const idToken = JSON.stringify({ sub: `google-${email}`, email, email_verified: true })
    return (await signInWithCredential(auth, GoogleAuthProvider.credential(idToken))).user.uid
  }
}

/** Google sign-in popup: the only place Google's own sign-in scripts are loaded. */
export const signInWithGoogle = () => signInWithPopup(auth, googleProvider, browserPopupRedirectResolver)
