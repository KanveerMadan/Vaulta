import { useMotionValueEvent, useScroll } from 'motion/react'
import StatementStage from './StatementStage'
import { CAPTIONS } from './story'

/**
 * The animated half of the story, loaded after the hero has painted: follows the captions'
 * scroll position and reports which caption is current.
 */
export default function StageDriver({ captions, onStep }) {
  const { scrollYProgress } = useScroll({ target: captions, offset: ['start 60%', 'end 60%'] })
  useMotionValueEvent(scrollYProgress, 'change', (p) => onStep(Math.min(CAPTIONS.length - 1, Math.floor(p * CAPTIONS.length))))
  return <StatementStage progress={scrollYProgress} />
}
