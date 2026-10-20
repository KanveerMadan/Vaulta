import { useEffect, useRef, useState } from 'react'

/** Fades and slides its children in once they scroll into view. With reduced motion they're simply there. */
export default function Reveal({ as: Tag = 'div', className = '', delay = 0, children, ...rest }) {
  const ref = useRef(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') { setShown(true); return undefined }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShown(true); io.disconnect() } }, { rootMargin: '0px 0px -10% 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <Tag ref={ref} style={delay ? { transitionDelay: `${delay}ms` } : undefined}
      className={`motion-safe:transition motion-safe:duration-700 motion-safe:ease-out ${shown ? '' : 'motion-safe:opacity-0 motion-safe:translate-y-4'} ${className}`} {...rest}>
      {children}
    </Tag>
  )
}
