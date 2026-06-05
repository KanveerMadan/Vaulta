import { useState, useRef, useEffect } from 'react'
import { Send, Sparkles } from 'lucide-react'
import { useFinanceStore } from '../store/financeStore'
import api from '../lib/api'
import clsx from 'clsx'

const STARTERS = [
  'How much did I spend on food this month?',
  'What are my top 3 expenses?',
  'Am I going to overshoot my budget?',
  'Kitna kharch hua last hafte?',
]

export default function ChatPanel() {
  const [input, setInput] = useState('')
  const { chatMessages, chatLoading, addChatMessage, setChatLoading } = useFinanceStore()
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, chatLoading])

  const send = async (text) => {
    const message = text || input.trim()
    if (!message || chatLoading) return
    setInput('')

    addChatMessage({ role: 'user', content: message })
    setChatLoading(true)

    try {
      const { data } = await api.post('/api/chat', { message })
      addChatMessage({ role: 'assistant', content: data.reply })
    } catch {
      addChatMessage({ role: 'assistant', content: 'Something went wrong. Try again.' })
    } finally {
      setChatLoading(false)
    }
  }

  return (
    <aside className="w-80 shrink-0 hidden lg:flex flex-col bg-card border border-border rounded-2xl overflow-hidden h-[calc(100vh-7rem)] sticky top-20">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        <div className="w-6 h-6 rounded-lg bg-brand-dim flex items-center justify-center">
          <Sparkles size={12} className="text-brand" />
        </div>
        <span className="text-t1 text-sm font-medium">AI Chat</span>
        <span className="ml-auto text-xs text-t3">Ask anything</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {chatMessages.length === 0 ? (
          <div className="space-y-2">
            <p className="text-t3 text-xs mb-3">Try asking:</p>
            {STARTERS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="w-full text-left text-xs text-t2 hover:text-t1 bg-elevated hover:bg-border border border-border rounded-xl px-3 py-2.5 transition-all duration-150"
              >
                {s}
              </button>
            ))}
          </div>
        ) : (
          chatMessages.map((msg, i) => (
            <div key={i} className={clsx('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div
                className={clsx(
                  'max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed',
                  msg.role === 'user'
                    ? 'bg-brand text-white rounded-br-sm'
                    : 'bg-elevated text-t1 border border-border rounded-bl-sm'
                )}
              >
                {msg.content}
              </div>
            </div>
          ))
        )}

        {chatLoading && (
          <div className="flex justify-start">
            <div className="bg-elevated border border-border rounded-xl rounded-bl-sm px-3 py-2.5 flex gap-1">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-t3 animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-border">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Ask about your money..."
            className="flex-1 bg-elevated border border-border rounded-xl px-3 py-2.5 text-xs text-t1 placeholder-t3 focus:outline-none focus:border-brand transition-colors"
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || chatLoading}
            className="w-9 h-9 rounded-xl bg-brand hover:bg-brand-light disabled:opacity-40 flex items-center justify-center transition-all active:scale-95"
          >
            <Send size={13} className="text-white" />
          </button>
        </div>
      </div>
    </aside>
  )
}