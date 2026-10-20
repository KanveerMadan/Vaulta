import { SHOTS } from './shots'

/** A real screen from the demo account (scripts/landing-shots), at 1x and 2x, with its size set. */
export default function Shot({ name, alt, className = '', eager = false }) {
  const { w, h } = SHOTS[name]
  return (
    <img src={`/landing/${name}.webp`} srcSet={`/landing/${name}.webp 1x, /landing/${name}@2x.webp 2x`} width={w} height={h}
      alt={alt} loading={eager ? 'eager' : 'lazy'} decoding="async" fetchPriority={eager ? 'high' : undefined}
      className={`block w-full h-auto ${className}`} />
  )
}

/** A phone around a full screen. */
export function Phone({ name, alt, eager }) {
  return (
    <div className="relative mx-auto w-[min(19rem,78vw)] rounded-[2.6rem] bg-ink p-2.5 shadow-3">
      <div className="absolute left-1/2 top-3.5 z-10 h-5 w-24 -translate-x-1/2 rounded-full bg-ink" aria-hidden="true" />
      <div className="overflow-hidden rounded-[2.1rem] bg-canvas">
        <div className="h-7 bg-surface" aria-hidden="true" />
        <Shot name={name} alt={alt} eager={eager} />
      </div>
    </div>
  )
}

/** A cutout of the app: a card with the screen inside, faded at the bottom when it's cropped. */
export function Cutout({ name, alt, maxH = '', inset = false }) {
  return (
    <div className={`relative overflow-hidden rounded-lg border border-line shadow-2 ${inset ? 'bg-canvas p-5' : 'bg-surface'} ${maxH}`}>
      <Shot name={name} alt={alt} />
      {maxH && <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-surface to-transparent" aria-hidden="true" />}
    </div>
  )
}
