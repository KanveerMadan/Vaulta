import { useState } from 'react'
import { Desktop, Moon, Sun } from '@phosphor-icons/react'
import { getThemeChoice, setThemeChoice } from '../lib/theme'

const OPTIONS = [['system', 'System', Desktop], ['light', 'Light', Sun], ['dark', 'Dark', Moon]]

/** System / light / dark, as a radio group. */
export default function ThemeSwitch({ compact = false }) {
  const [choice, setChoice] = useState(getThemeChoice)
  const pick = (value) => { setThemeChoice(value); setChoice(value) }
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-sm border border-line bg-sunken p-0.5">
      {OPTIONS.map(([value, label, Icon]) => (
        <button key={value} role="radio" aria-checked={choice === value} onClick={() => pick(value)} title={label}
          className={`flex items-center gap-1.5 rounded-[6px] px-2.5 h-8 text-micro font-medium transition-colors duration-fast
            ${choice === value ? 'bg-surface text-ink shadow-1' : 'text-muted hover:text-ink'}`}>
          <Icon size={14} aria-hidden />{compact ? <span className="sr-only">{label}</span> : label}
        </button>
      ))}
    </div>
  )
}
