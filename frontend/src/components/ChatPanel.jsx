import { useState, useRef, useEffect } from 'react'
import { useFinanceStore } from '../store/financeStore'
import api from '../lib/api'
import clsx from 'clsx'

const STARTERS = [
  "How's my budget this month?",
  'What takes most of my money?',
  'Compare this month to last month',
]

function newSessionId() {
  try {
    const saved = sessionStorage.getItem('vaulta-chat-session')
    if (saved) return saved
    const id = crypto.randomUUID()
    sessionStorage.setItem('vaulta-chat-session', id)
    return id
  } catch {
    return crypto.randomUUID()
  }
}

function Table({ table }) {
  return (
    <div className="mt-2 overflow-x-auto">
      <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: '#8FAF98' }}>{table.title}</p>
      <table className="w-full text-[11px]">
        <thead>
          <tr>{table.columns.map((c, i) => <th key={i} className={clsx('font-medium pb-1', i ? 'text-right' : 'text-left')} style={{ color: '#7A9E80' }}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr key={r} style={{ borderTop: '1px solid #F2F7F3' }}>
              {row.map((cell, i) => <td key={i} className={clsx('py-0.5', i ? 'text-right font-mono' : '')}>{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ActionCard({ action, onDone }) {
  const [state, setState] = useState('open') // open | busy | done
  const [result, setResult] = useState(null)
  const decide = async (decision) => {
    setState('busy')
    try {
      const { data } = await api.post('/api/chat/confirm', { token: action.token, decision })
      setResult(data.message)
      if (data.ok) onDone?.()
    } catch (err) {
      setResult(err?.response?.data?.detail || "Couldn't do that. Ask again.")
    }
    setState('done')
  }
  return (
    <div className="mt-2 rounded-lg p-2.5" style={{ background: '#F2F7F3', border: '1px solid #D4E4D7' }}>
      <p className="text-[11px] font-medium" style={{ color: '#1A2E1E' }}>{action.summary}</p>
      {action.read_only ? (
        <p className="text-[11px] mt-1" style={{ color: '#4A6B50' }} role="note">{action.note}</p>
      ) : state === 'done' ? (
        <p className="text-[11px] mt-1" style={{ color: '#4A6B50' }}>{result}</p>
      ) : (
        <div className="flex gap-2 mt-2">
          <button onClick={() => decide('confirm')} disabled={state === 'busy'}
            className="text-[11px] px-2.5 py-1 rounded-md font-medium disabled:opacity-50" style={{ background: '#2D6A4F', color: '#F2F7F3' }}>Confirm</button>
          <button onClick={() => decide('cancel')} disabled={state === 'busy'}
            className="text-[11px] px-2.5 py-1 rounded-md disabled:opacity-50" style={{ color: '#4A6B50' }}>Cancel</button>
        </div>
      )}
    </div>
  )
}

export default function ChatPanel() {
  const [input, setInput] = useState('')
  const [disabled, setDisabled] = useState(false)
  const [sessionId, setSessionId] = useState(newSessionId)
  const { chatMessages, chatLoading, addChatMessage, setChatLoading, setChatMessages,
    chatOpen, setChatOpen, takePendingQuestion } = useFinanceStore()
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
      const { data } = await api.post('/api/chat', { message, session_id: sessionId })
      addChatMessage({ role: 'assistant', content: data.reply, tables: data.tables, actions: data.actions })
    } catch (err) {
      if (err?.response?.status === 403) {
        setDisabled(true)
        setChatMessages([])
      } else {
        addChatMessage({ role: 'assistant', content: err?.response?.status === 429 ? err.response.data.detail : "Couldn't reach the server. Please try again." })
      }
    } finally { setChatLoading(false) }
  }

  // The home ask bar puts a question in the store; send it from here
  const sendRef = useRef(send)
  useEffect(() => { sendRef.current = send })
  useEffect(() => useFinanceStore.subscribe((state) => {
    if (state.pendingQuestion) sendRef.current(takePendingQuestion())
  }), [takePendingQuestion])

  const enable = async () => {
    await api.patch('/api/settings', { ai_chat_enabled: true })
    setDisabled(false)
  }

  const clear = async () => {
    await api.delete('/api/chat/history')
    setChatMessages([])
    try { sessionStorage.removeItem('vaulta-chat-session') } catch { /* private mode */ }
    setSessionId(newSessionId())
  }

  return (
    <aside aria-label="AI Assistant"
      className={clsx('flex-col overflow-hidden lg:w-72 lg:shrink-0 lg:rounded-xl lg:sticky lg:top-20 lg:h-[calc(100vh-5.5rem)] lg:flex',
        chatOpen ? 'flex fixed inset-0 z-50 lg:static lg:inset-auto' : 'hidden')}
      style={{ background: '#FFFFFF', border: '1px solid #D4E4D7', boxShadow: '0 1px 3px rgba(45,106,79,0.06), 0 4px 16px rgba(45,106,79,0.04)' }}>

      <div className="px-4 py-3.5 flex items-center justify-between" style={{ borderBottom: '1px solid #E8F0EA' }}>
        <div>
          <p className="text-sm font-semibold" style={{ color: '#1A2E1E' }}>AI Assistant</p>
          <p className="text-xs mt-0.5" style={{ color: '#7A9E80' }}>Answers from your own numbers</p>
        </div>
        <div className="flex items-center gap-1">
          {chatMessages.length > 0 && !disabled && (
            <button onClick={clear} className="text-[11px] px-2" style={{ color: '#8FAF98' }} title="Clear conversation">Clear</button>
          )}
          <button onClick={() => setChatOpen(false)} className="lg:hidden text-sm px-2" style={{ color: '#4A6B50' }} aria-label="Close assistant">✕</button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3" style={{ background: '#F2F7F3' }}>
        {disabled ? (
          <div className="text-xs space-y-3" style={{ color: '#4A6B50' }}>
            <p>AI chat is turned off. Your questions and the figures needed to answer them go to an AI service only while it's on.</p>
            <button onClick={enable} className="px-3 py-1.5 rounded-md font-medium" style={{ background: '#2D6A4F', color: '#F2F7F3' }}>
              Turn on AI chat
            </button>
          </div>
        ) : chatMessages.length === 0 ? (
          <div className="space-y-2 animate-fade-in">
            <p className="text-xs mb-3" style={{ color: '#8FAF98' }}>Suggested questions</p>
            {STARTERS.map(s => (
              <button key={s} onClick={() => send(s)}
                className="w-full text-left text-xs rounded-lg px-3 py-2.5 transition-all duration-150 leading-relaxed"
                style={{ background: '#FFFFFF', border: '1px solid #D4E4D7', color: '#4A6B50' }}>
                {s}
              </button>
            ))}
          </div>
        ) : (
          chatMessages.map((msg, i) => (
            <div key={i} className={clsx('flex animate-fade-up', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div className="max-w-[92%] rounded-xl px-3 py-2 text-xs leading-relaxed"
                style={msg.role === 'user' ? {
                  background: '#2D6A4F', color: '#F2F7F3', borderBottomRightRadius: '4px',
                } : {
                  background: '#FFFFFF', border: '1px solid #D4E4D7', color: '#1A2E1E', borderBottomLeftRadius: '4px',
                  boxShadow: '0 1px 3px rgba(45,106,79,0.06)',
                }}>
                <p className="whitespace-pre-wrap">{msg.content}</p>
                {msg.tables?.map((t, j) => <Table key={j} table={t} />)}
                {msg.actions?.map((a) => <ActionCard key={a.token} action={a} />)}
              </div>
            </div>
          ))
        )}

        {chatLoading && (
          <div className="flex justify-start">
            <div className="rounded-xl px-3.5 py-3 flex gap-1"
              style={{ background: '#FFFFFF', border: '1px solid #D4E4D7', borderBottomLeftRadius: '4px' }}>
              {[0, 1, 2].map(i => (
                <div key={i} className="w-1.5 h-1.5 rounded-full animate-skeleton" style={{ background: '#B8CFC0', animationDelay: `${i * 0.15}s` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {!disabled && (
        <div className="p-3" style={{ borderTop: '1px solid #E8F0EA', background: '#FFFFFF' }}>
          <div className="flex gap-2">
            <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()}
              placeholder="Ask anything about your money…" maxLength={1000} aria-label="Ask the assistant"
              className="input" style={{ fontSize: '0.75rem', padding: '0.5rem 0.75rem' }} />
            <button onClick={() => send()} disabled={!input.trim() || chatLoading} aria-label="Send"
              className="w-8 h-8 rounded-lg flex items-center justify-center transition-all active:scale-95 shrink-0 disabled:opacity-30"
              style={{ background: '#2D6A4F' }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#F2F7F3" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </aside>
  )
}
