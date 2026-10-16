// Firebase App Check: proves API requests come from this app in a real browser (backend app/core/appcheck.py).
// Sent by signed-in users (any request may create their account) and on the anonymous routes bots would abuse,
// so reCAPTCHA isn't loaded for visitors just reading the landing page.
//   VITE_RECAPTCHA_ENTERPRISE_SITE_KEY   production: reCAPTCHA Enterprise through the App Check SDK
//   VITE_APPCHECK_DEBUG_TOKEN            local and browser-test builds only: sent as-is (the API accepts it outside
//                                        production); never compiled into a production build
export const APP_CHECKED = [/^\/auth\/demo$/, /^\/auth\/me$/, /^\/auth\/password-reset-requested$/, /^\/api\/import\/batch$/, /^\/api\/chat$/]

let instance = null

export async function appCheckToken() {
  if (import.meta.env.MODE !== 'production' && import.meta.env.VITE_APPCHECK_DEBUG_TOKEN) return import.meta.env.VITE_APPCHECK_DEBUG_TOKEN
  const siteKey = import.meta.env.VITE_RECAPTCHA_ENTERPRISE_SITE_KEY
  if (!siteKey) return null
  const [{ initializeAppCheck, ReCaptchaEnterpriseProvider, getToken }, { app }] = await Promise.all([import('firebase/app-check'), import('./firebase')])
  instance ??= initializeAppCheck(app, { provider: new ReCaptchaEnterpriseProvider(siteKey), isTokenAutoRefreshEnabled: true })
  try {
    return (await getToken(instance, false)).token
  } catch {
    return null                      // the API decides (monitor mode lets it through; enforcement refuses)
  }
}
