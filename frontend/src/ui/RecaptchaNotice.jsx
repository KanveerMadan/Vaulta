/** The notice Google requires when reCAPTCHA's badge is hidden (lib/recaptcha.js). Links only: nothing loads from Google. */
export default function RecaptchaNotice({ className = '' }) {
  return (
    <p className={`text-xs text-muted ${className}`}>
      Protected by reCAPTCHA: Google's <a className="underline" href="https://policies.google.com/privacy" target="_blank" rel="noreferrer">Privacy Policy</a> and{' '}
      <a className="underline" href="https://policies.google.com/terms" target="_blank" rel="noreferrer">Terms of Service</a> apply.
    </p>
  )
}
