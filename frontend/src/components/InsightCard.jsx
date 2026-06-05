import { Sparkles, RefreshCw } from 'lucide-react'
import { useState } from 'react'

const INSIGHTS = [
  {
    text: "You order food every time you're awake past midnight. It's happened 12 times this month — ₹4,200 spent.",
    type: 'warning',
  },
  {
    text: "You haven't opened Zee5 in 47 days. It's costing you ₹499/month silently.",
    type: 'alert',
  },
  {
    text: "Your food spend is 37% of total expenses — ₹9,200. The Indian average is 22%.",
    type: 'info',
  },
]

export default function InsightCard() {
  const [idx, setIdx] = useState(0)
  const insight = INSIGHTS[idx]

  return (
    <div className="bg-card border border-brand/20 rounded-2xl p-5 h-full flex flex-col relative overflow-hidden">
      {/* Glow */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-brand opacity-[0.04] rounded-full blur-2xl -translate-y-1/2 translate-x-1/2 pointer-events-none" />

      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles size={13} className="text-brand" />
          <span className="text-brand text-xs font-medium">AI Insight</span>
        </div>
        <button
          onClick={() => setIdx((idx + 1) % INSIGHTS.length)}
          className="text-t3 hover:text-t1 transition-colors"
        >
          <RefreshCw size={12} />
        </button>
      </div>

      <p className="text-t1 text-sm leading-relaxed flex-1">{insight.text}</p>

      <div className="mt-4 pt-3 border-t border-border">
        <p className="text-t3 text-xs">Updated daily · Powered by Groq</p>
      </div>
    </div>
  )
}