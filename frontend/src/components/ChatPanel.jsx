import { useState, useRef, useEffect } from 'react'
import { ArrowUp, Check, Lock, Sparkle, Trash, X } from '@phosphor-icons/react'
import { useFinanceStore } from '../store/financeStore'
import api from '../lib/api'

const STARTERS = [
  "How's my budget this month?",
  'What takes most of my money?',
  'Compare this month to last month',
]
const WORDS_PER_TICK = 2
const TICK_MS = 28
const reduceMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

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

/** The reply appears a few words at a time (instantly with reduced motion). Screen readers get it whole. */
function Typed({ text, animate }) {
  const words = text.split(/(\s+)/)
  const [count, setCount] = useState(animate && !reduceMotion() ? 0 : words.length)
  useEffect(() => {
    if (count >= words.length) return undefined
    const id = setTimeout(() => setCount((c) => c + WORDS_PER_TICK * 2), TICK_MS)
    return () => clearTimeout(id)
  }, [count, words.length])
  return (
    <>
      <p className="whitespace-pre-wrap" aria-hidden="true">{words.slice(0, count).join('')}</p>
      <p className="sr-only">{text}</p>
    </>
  )
}

function Table({ table }) {
  return (
    <div className="mt-3 rounded-sm border border-line bg-surface overflow-hidden">
      <p className="px-3 pt-2 pb-1 eyebrow">{table.title}</p>
      <table className="w-full text-[13px] stack-table">
        <thead>
          <tr className="text-muted">{table.columns.map((c, i) => <th key={i} className={`font-medium px-3 py-1.5 ${i ? 'text-right' : 'text-left'}`}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr key={r} className="border-t border-line">
              {row.map((cell, i) => (
                <td key={i} data-label={i ? table.columns[i] : undefined} className={`px-3 py-1.5 ${i ? 'text-right num text-ink' : 'text-ink-2'}`}>{cell}</td>
              ))}
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
    <div className="mt-3 rounded-sm border border-accent-line bg-accent-tint/60 p-3">
      <p className="eyebrow mb-1">Confirm a change</p>
      <p className="text-sm font-medium text-ink">{action.summary}</p>
      {action.read_only ? (
        <p className="mt-2 flex items-start gap-1.5 text-[13px] text-ink-2" role="note"><Lock size={14} className="mt-0.5 shrink-0" aria-hidden />{action.note}</p>
      ) : state === 'done' ? (
        <p className="mt-2 text-[13px] text-ink-2" role="status">{result}</p>
      ) : (
        <div className="flex gap-2 mt-3">
          <button onClick={() => decide('confirm')} disabled={state === 'busy'} className="btn-primary h-9 px-3 text-[13px]"><Check size={14} aria-hidden />Confirm</button>
          <button onClick={() => decide('cancel')} disabled={state === 'busy'} className="btn-quiet h-9 text-[13px]">Cancel</button>
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
    bottomRef.current?.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'end' })
  }, [chatMessages, chatLoading])

  const send = async (text) => {
    const message = (text || input).trim()
    if (!message || chatLoading) return
    setInput('')
    addChatMessage({ role: 'user', content: message })
    setChatLoading(true)
    try {
      const { data } = await api.post('/api/chat', { message, session_id: sessionId })
      addChatMessage({ role: 'assistant', content: data.reply, tables: data.tables, actions: data.actions, fresh: true })
    } catch (err) {
      if (err?.response?.status === 403 && !err.response.data?.detail?.includes('demo')) {
        setDisabled(true)
        setChatMessages([])
      } else {
        addChatMessage({ role: 'assistant', content: err?.response?.status === 429 ? err.response.data.detail : "Couldn't reach the server. Please try again." })
      }
    } finally { setChatLoading(false) }
  }

  // The home ask bar and the command palette put a question in the store; send it from here
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
      className={`flex-col bg-surface xl:sticky xl:top-0 xl:h-dvh xl:flex xl:border-l xl:border-line
        ${chatOpen ? 'flex fixed inset-0 z-50 xl:static' : 'hidden'}`}>
      <header className="h-14 px-4 flex items-center justify-between border-b border-line shrink-0">
        <div className="flex items-center gap-2">
          <Sparkle size={16} className="text-accent-text" aria-hidden />
          <div>
            <p className="text-sm font-semibold text-ink leading-tight">Ask Vaulta</p>
            <p className="text-micro text-muted leading-tight">Answers from your own numbers</p>
          </div>
        </div>
        <div className="flex items-center">
          {chatMessages.length > 0 && !disabled && (
            <button onClick={clear} className="btn-quiet h-9 text-micro" title="Clear conversation"><Trash size={14} aria-hidden />Clear</button>
          )}
          <button onClick={() => setChatOpen(false)} className="xl:hidden btn-quiet w-10 h-10 !p-0" aria-label="Close assistant"><X size={18} /></button>
        </div>
      </header>

      <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-4 space-y-4 bg-canvas" aria-live="polite">
        {disabled ? (
          <div className="text-sm space-y-3 text-ink-2">
            <p>AI chat is turned off. Your questions and the figures needed to answer them go to an AI service only while it's on.</p>
            <button onClick={enable} className="btn-primary">Turn on AI chat</button>
          </div>
        ) : chatMessages.length === 0 ? (
          <div className="space-y-2">
            <p className="text-sm text-muted mb-3">Try asking</p>
            {STARTERS.map((s) => (
              <button key={s} onClick={() => send(s)}
                className="w-full text-left text-sm rounded-sm px-3 py-2.5 border border-line bg-surface text-ink-2 hover:border-accent-line hover:text-ink transition-colors duration-fast">
                {s}
              </button>
            ))}
          </div>
        ) : (
          chatMessages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'user' ? (
                <div className="max-w-[88%] rounded-md rounded-br-sm bg-inverse text-on-inverse px-3 py-2 text-sm">{msg.content}</div>
              ) : (
                <div className="max-w-full w-full text-sm text-ink leading-relaxed">
                  <Typed text={msg.content} animate={msg.fresh && i === chatMessages.length - 1} />
                  {msg.tables?.map((t, j) => <Table key={j} table={t} />)}
                  {msg.actions?.map((a) => <ActionCard key={a.token} action={a} />)}
                </div>
              )}
            </div>
          ))
        )}
        {chatLoading && (
          <div className="flex gap-1 py-1" aria-label="Vaulta is answering">
            {[0, 1, 2].map((i) => <span key={i} className="w-1.5 h-1.5 rounded-full bg-faint animate-pulse" style={{ animationDelay: `${i * 0.15}s` }} />)}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {!disabled && (
        <form className="p-3 border-t border-line bg-surface shrink-0 safe-bottom" onSubmit={(e) => { e.preventDefault(); send() }}>
          <div className="flex items-end gap-2 rounded-md border border-line-strong bg-surface px-3 py-2 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
            <input value={input} onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your money…" maxLength={1000} aria-label="Ask the assistant"
              className="flex-1 bg-transparent text-sm text-ink placeholder:text-muted outline-none min-h-[28px]" />
            <button type="submit" disabled={!input.trim() || chatLoading} aria-label="Send"
              className="w-8 h-8 rounded-sm bg-accent text-on-accent flex items-center justify-center disabled:opacity-30 transition-opacity">
              <ArrowUp size={16} weight="bold" />
            </button>
          </div>
        </form>
      )}
    </aside>
  )
}
