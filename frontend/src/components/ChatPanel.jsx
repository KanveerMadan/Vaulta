import { useState, useRef, useEffect } from 'react'
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
    const message = (text || input).trim()
    if (!message || chatLoading) return
    setInput('')
    addChatMessage({ role: 'user', content: message })
    setChatLoading(true)
    try {
      const { data } = await api.post('/api/chat', { message })
      addChatMessage({ role: 'assistant', content: data.reply })
    } catch {
      addChatMessage({ role: 'assistant', content: "Couldn't reach the server. Please try again." })
    } finally { setChatLoading(false) }
  }

  return (
    <aside className="w-72 shrink-0 hidden lg:flex flex-col rounded-xl overflow-hidden sticky top-20 h-[calc(100vh-5.5rem)]"
      style={{ background: '#FFFFFF', border: '1px solid #D4E4D7', boxShadow: '0 1px 3px rgba(45,106,79,0.06), 0 4px 16px rgba(45,106,79,0.04)' }}>

      <div className="px-4 py-3.5 flex items-center justify-between"
        style={{ borderBottom: '1px solid #E8F0EA' }}>
        <div>
          <p className="text-sm font-semibold" style={{ color: '#1A2E1E' }}>AI Assistant</p>
          <p className="text-xs mt-0.5" style={{ color: '#7A9E80' }}>Ask about your money</p>
        </div>
        <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: '#2D6A4F' }} />
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3" style={{ background: '#F2F7F3' }}>
        {chatMessages.length === 0 ? (
          <div className="space-y-2 animate-fade-in">
            <p className="text-xs mb-3" style={{ color: '#8FAF98' }}>Suggested questions</p>
            {STARTERS.map(s => (
              <button key={s} onClick={() => send(s)}
                className="w-full text-left text-xs rounded-lg px-3 py-2.5 transition-all duration-150 leading-relaxed"
                style={{ background: '#FFFFFF', border: '1px solid #D4E4D7', color: '#4A6B50' }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = '#8FAF98'; e.currentTarget.style.color = '#2D6A4F' }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = '#D4E4D7'; e.currentTarget.style.color = '#4A6B50' }}
              >
                {s}
              </button>
            ))}
          </div>
        ) : (
          chatMessages.map((msg, i) => (
            <div key={i} className={clsx('flex animate-fade-up', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div className={clsx('max-w-[88%] rounded-xl px-3 py-2 text-xs leading-relaxed')}
                style={msg.role === 'user' ? {
                  background: '#2D6A4F',
                  color: '#F2F7F3',
                  borderBottomRightRadius: '4px',
                } : {
                  background: '#FFFFFF',
                  border: '1px solid #D4E4D7',
                  color: '#1A2E1E',
                  borderBottomLeftRadius: '4px',
                  boxShadow: '0 1px 3px rgba(45,106,79,0.06)',
                }}>
                {msg.content}
              </div>
            </div>
          ))
        )}

        {chatLoading && (
          <div className="flex justify-start">
            <div className="rounded-xl px-3.5 py-3 flex gap-1"
              style={{ background: '#FFFFFF', border: '1px solid #D4E4D7', boxShadow: '0 1px 3px rgba(45,106,79,0.06)', borderBottomLeftRadius: '4px' }}>
              {[0,1,2].map(i => (
                <div key={i} className="w-1.5 h-1.5 rounded-full animate-skeleton"
                  style={{ background: '#B8CFC0', animationDelay: `${i * 0.15}s` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="p-3" style={{ borderTop: '1px solid #E8F0EA', background: '#FFFFFF' }}>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
            placeholder="Ask anything..."
            className="input"
            style={{ fontSize: '0.75rem', padding: '0.5rem 0.75rem' }}
          />
          <button onClick={() => send()} disabled={!input.trim() || chatLoading}
            className="w-8 h-8 rounded-lg flex items-center justify-center transition-all active:scale-95 shrink-0 disabled:opacity-30"
            style={{ background: '#2D6A4F' }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#F2F7F3" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>
    </aside>
  )
}