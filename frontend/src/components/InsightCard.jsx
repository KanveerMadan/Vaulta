import { useState } from 'react'

const INSIGHTS = [
  {
    tag: 'Pattern detected',
    tagClass: 'tag-warning',
    headline: 'Late-night food habit',
    body: "You order food every time you're awake past midnight. 12 times this month — ₹4,200 spent.",
  },
  {
    tag: 'Action needed',
    tagClass: 'tag-negative',
    headline: 'Silent subscription drain',
    body: "You haven't opened Zee5 in 47 days. It's costing ₹499/month silently.",
  },
  {
    tag: 'Benchmark',
    tagClass: 'tag-positive',
    headline: 'Food spend above average',
    body: 'Your food spend is 37% of total expenses. The Indian urban average is 22%.',
  },
]

export default function InsightCard() {
  const [idx, setIdx] = useState(0)
  const insight = INSIGHTS[idx]

  return (
    <div className="card shadow-card p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#27602F" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
          </svg>
          <p className="text-forest-600 text-xs font-semibold uppercase tracking-widest">AI Insight</p>
        </div>
        <div className="flex items-center gap-1.5">
          {INSIGHTS.map((_, i) => (
            <button key={i} onClick={() => setIdx(i)}
              className={`rounded-full transition-all duration-200 ${i === idx ? 'w-4 h-1.5 bg-forest-600' : 'w-1.5 h-1.5 bg-cream-400 hover:bg-cream-500'}`}
            />
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-3">
        <span className={insight.tagClass}>{insight.tag}</span>
        <p className="font-display text-xl font-light text-forest-900 leading-snug mt-2">{insight.headline}</p>
        <p className="text-forest-600 text-sm leading-relaxed">{insight.body}</p>
      </div>

      <div className="mt-4 pt-4 border-t border-cream-300 flex items-center justify-between">
        <p className="text-forest-400 text-xs">Updated daily · Groq</p>
        <button className="text-forest-600 hover:text-forest-900 text-xs font-medium transition-colors">
          Ask AI →
        </button>
      </div>
    </div>
  )
}