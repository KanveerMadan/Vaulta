import { useState } from 'react'

const INSIGHTS = [
  {
    headline: 'Late-night food habit',
    body: "You order food every time you're awake past midnight. It's happened 12 times this month — ₹4,200 spent.",
    tag: 'Pattern detected',
    tagColor: 'text-gold border-gold/30 bg-gold/10',
  },
  {
    headline: 'Silent subscription drain',
    body: "You haven't opened Zee5 in 47 days. It's costing you ₹499/month without any use.",
    tag: 'Action needed',
    tagColor: 'text-danger border-danger/30 bg-danger/10',
  },
  {
    headline: 'Food spend above average',
    body: 'Your food spend is 37% of total expenses. The Indian urban average is 22%.',
    tag: 'Benchmark',
    tagColor: 'text-forest-200 border-forest-500 bg-forest-800',
  },
]

export default function InsightCard() {
  const [idx, setIdx] = useState(0)
  const insight = INSIGHTS[idx]

  return (
    <div className="card p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6DB87A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <p className="text-forest-200 text-xs font-medium uppercase tracking-widest">AI Insight</p>
        </div>
        <div className="flex items-center gap-2">
          {INSIGHTS.map((_, i) => (
            <button key={i} onClick={() => setIdx(i)}
              className={`w-1.5 h-1.5 rounded-full transition-all ${i === idx ? 'bg-cream-300' : 'bg-forest-700'}`}
            />
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-3">
        <span className={`inline-flex text-xs font-medium px-2 py-0.5 rounded border ${insight.tagColor}`}>
          {insight.tag}
        </span>
        <p className="font-display text-lg font-light text-cream-100 leading-snug">{insight.headline}</p>
        <p className="text-forest-200 text-sm leading-relaxed">{insight.body}</p>
      </div>

      <div className="mt-4 pt-4 border-t border-forest-700">
        <p className="text-forest-500 text-xs">Updated daily · Powered by Groq</p>
      </div>
    </div>
  )
}