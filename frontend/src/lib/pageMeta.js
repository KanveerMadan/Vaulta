// Search and share metadata. The public pages below get their own title, description and canonical URL on
// vaulta.in; public/robots.txt and public/sitemap.xml list the same pages (pageMeta.test.js keeps them in step).
// Everything else is the signed-in app: no canonical, and robots.txt keeps crawlers out.
export const SITE = 'https://vaulta.in'
export const DEFAULT_TITLE = 'Vaulta: every rupee, tracked'
export const DEFAULT_DESCRIPTION = 'Vaulta tracks every rupee you spend, automatically. Statements are read on your device; you just ask.'

export const PUBLIC_PAGES = {
  '/welcome': { title: DEFAULT_TITLE, description: 'Vaulta tracks every rupee you spend, automatically. Your statements are read on your phone; only clean transaction rows reach us. Try the demo, no sign-up needed.' },
  '/security': { title: 'Security and privacy · Vaulta', description: 'How Vaulta protects your money data: what is read on your device, what reaches our servers, how it is encrypted, and what is never collected.' },
  '/privacy': { title: 'Privacy policy · Vaulta', description: 'What Vaulta collects and why, what it never collects, who else handles it, how long it is kept, and your rights.' },
  '/terms': { title: 'Terms of service · Vaulta', description: 'The terms for using Vaulta: it is free, your data stays yours, it is not financial advice, and you can export or delete everything at any time.' },
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
