import { useRef } from 'react'
import { useScroll } from 'motion/react'
import StatementStage from './StatementStage'

/** The statement being taken apart, scrubbed by the "Why Vaulta" section's own scroll (loaded when it comes near). */
export default function WhyStage({ section }) {
  const fallback = useRef(null)
  const { scrollYProgress } = useScroll({ target: section || fallback, offset: ['start 75%', 'end 60%'] })
  return <StatementStage progress={scrollYProgress} />
}
