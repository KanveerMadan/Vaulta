// Search and share metadata. The public pages below get their own title, description and canonical URL on
// vaulta.in; public/robots.txt and public/sitemap.xml list the same pages (pageMeta.test.js keeps them in step).
// Everything else is the signed-in app: no canonical, and robots.txt keeps crawlers out.
export const SITE = 'https://vaulta.in'
export const DEFAULT_TITLE = 'vaulta.in: Private Expense Tracker for India'
export const DEFAULT_DESCRIPTION = 'Track your UPI and card spending in India without a bank login: vaulta.in reads your bank statement on your device, sorts your payments, keeps you on budget and answers questions about your money.'

export const PUBLIC_PAGES = {
  '/welcome': { title: DEFAULT_TITLE, description: DEFAULT_DESCRIPTION },
  '/security': { title: 'Security and privacy · vaulta.in', description: 'How vaulta.in protects your money data: what is read on your device, what reaches our servers, how it is encrypted, and what is never collected.' },
  '/privacy': { title: 'Privacy policy · vaulta.in', description: 'What vaulta.in collects and why, what it never collects, who else handles it, how long it is kept, and your rights.' },
  '/terms': { title: 'Terms of service · vaulta.in', description: 'The terms for using vaulta.in: it is free, your data stays yours, it is not financial advice, and you can export or delete everything at any time.' },
}

function tag(selector, create) {
  let el = document.head.querySelector(selector)
  if (!el && create) { el = create(); document.head.appendChild(el) }
  return el
}

export function applyPageMeta(pathname) {
  const page = PUBLIC_PAGES[pathname]
  document.title = page?.title ?? DEFAULT_TITLE
  tag('meta[name="description"]', () => Object.assign(document.createElement('meta'), { name: 'description' }))
    .setAttribute('content', page?.description ?? DEFAULT_DESCRIPTION)
  if (page) {
    tag('link[rel="canonical"]', () => Object.assign(document.createElement('link'), { rel: 'canonical' })).href = SITE + pathname
  } else {
    tag('link[rel="canonical"]')?.remove()
  }
}
