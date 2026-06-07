import { useState } from 'react'

const INSIGHTS = [
  {
    tag: 'Pattern detected', tagClass: 'tag-warning',
    headline: 'Late-night food habit',
    body: "You order food every time you're awake past midnight. 12 times this month — ₹4,200 spent.",
  },
  {
    tag: 'Action needed', tagClass: 'tag-negative',
    headline: 'Silent subscription drain',
    body: "You haven't opened Zee5 in 47 days. It's costing ₹499/month silently.",
  },
  {
    tag: 'Benchmark', tagClass: 'tag-positive',
    headline: 'Food spend above average',
    body: 'Your food spend is 37% of total expenses. The Indian urban average is 22%.',
  },
]

export default function InsightCard() {
  const [idx, setIdx] = useState(0)
  const insight = INSIGHTS[idx]

  return (
    <div className="card p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded-md flex items-center justify-center"
            style={{ background: '#E8F5EB' }}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#2D6A4F" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
          </div>
          <p className="label">AI Insight</p>
        </div>
        <div className="flex items-center gap-1.5">
          {INSIGHTS.map((_, i) => (
            <button key={i} onClick={() => setIdx(i)}
              className="rounded-full transition-all duration-200"
              style={{
                width: i === idx ? '16px' : '6px',
                height: '6px',
                background: i === idx ? '#2D6A4F' : '#D4E4D7',
              }}
            />
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-3">
        <span className={insight.tagClass}>{insight.tag}</span>
        <p className="font-display font-light leading-snug mt-2"
          style={{ fontSize: '1.2rem', color: '#1A2E1E' }}>
          {insight.headline}
        </p>
        <p className="text-sm leading-relaxed" style={{ color: '#4A6B50' }}>
          {insight.body}
        </p>
      </div>

      <div className="mt-4 pt-4 flex items-center justify-between"
        style={{ borderTop: '1px solid #E8F0EA' }}>
        <p className="text-xs" style={{ color: '#8FAF98' }}>Updated daily · Groq</p>
        <button className="text-xs font-medium transition-colors"
          style={{ color: '#2D6A4F' }}
          onMouseEnter={e => e.currentTarget.style.color = '#1A2E1E'}
          onMouseLeave={e => e.currentTarget.style.color = '#2D6A4F'}>
          Ask AI →
        </button>
      </div>
    </div>
  )
}