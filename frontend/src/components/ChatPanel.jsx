import { useState, useRef, useEffect } from 'react'
import { useFinanceStore } from '../store/financeStore'
import api from '../lib/api'
import clsx from 'clsx'

const STARTERS = [
  'How much did I spend on food this month?',
  'What are my top 3 expenses?',
  'Am I going to overshoot my budget?',
  'Kitna kharch hua last hafte food pe?',
]

export default function ChatPanel() {
  const [input, setInput] = useState('')
  const { chatMessages, chatLoading, addChatMessage, setChatLoading } = useFinanceStore()
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, chatLoading])

  const send = async (text) => {
    const message = (text || input).trim()
    if (!message || chatLoading) return
    setInput('')
    addChatMessage({ role: 'user', content: message })
    setChatLoading(true)
    try {
      const { data } = await api.post('/api/chat', { message })
      addChatMessage({ role: 'assistant', content: data.reply })
    } catch {
      addChatMessage({ role: 'assistant', content: "I couldn't reach the server. Please try again." })
    } finally {
      setChatLoading(false)
    }
  }

  return (
    <aside className="w-72 shrink-0 hidden lg:flex flex-col rounded-xl border border-forest-700 bg-forest-900 overflow-hidden sticky top-20 h-[calc(100vh-5.5rem)]">
      <div className="px-4 py-3.5 border-b border-forest-700 flex items-center justify-between">
        <div>
          <p className="text-cream-200 text-sm font-medium">AI Assistant</p>
          <p className="text-forest-400 text-xs mt-0.5">Ask about your money</p>
        </div>
        <div className="w-2 h-2 rounded-full bg-safe animate-pulse" title="Online" />
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {chatMessages.length === 0 ? (
          <div className="space-y-2 animate-fade-in">
            <p className="text-forest-400 text-xs mb-3">Suggested questions</p>
            {STARTERS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="w-full text-left text-xs text-forest-200 hover:text-cream-100 bg-forest-800 hover:bg-forest-700 border border-forest-700 hover:border-forest-500 rounded-lg px-3 py-2.5 transition-all duration-150 leading-relaxed"
              >
                {s}
              </button>
            ))}
          </div>
        ) : (
          chatMessages.map((msg, i) => (
            <div key={i} className={clsx('flex animate-fade-in', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div className={clsx(
                'max-w-[88%] rounded-xl px-3 py-2 text-xs leading-relaxed',
                msg.role === 'user'
                  ? 'bg-forest-600 text-cream-100 rounded-br-sm'
                  : 'bg-forest-800 border border-forest-700 text-cream-200 rounded-bl-sm'
              )}>
                {msg.content}
              </div>
            </div>
          ))
        )}

        {chatLoading && (
          <div className="flex justify-start">
            <div className="bg-forest-800 border border-forest-700 rounded-xl rounded-bl-sm px-3 py-2.5 flex gap-1">
              {[0,1,2].map(i => (
                <div key={i} className="w-1 h-1 rounded-full bg-forest-300 animate-skeleton"
                  style={{ animationDelay: `${i * 0.15}s` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-3 border-t border-forest-700">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Ask anything..."
            className="flex-1 bg-forest-800 border border-forest-700 focus:border-forest-400 rounded-lg px-3 py-2 text-xs text-cream-200 placeholder-forest-500 focus:outline-none transition-colors"
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || chatLoading}
            className="w-8 h-8 rounded-lg bg-cream-200 hover:bg-cream-50 disabled:opacity-30 flex items-center justify-center transition-all active:scale-95 shrink-0"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#0A1A0E" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  )
}