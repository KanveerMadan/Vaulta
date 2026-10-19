import { useSyncExternalStore } from 'react'

/** True while the media query matches (e.g. '(min-width: 1024px)'). */
export function useMedia(query) {
  return useSyncExternalStore(
    (onChange) => {
      const m = window.matchMedia(query)
      m.addEventListener('change', onChange)
      return () => m.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}
