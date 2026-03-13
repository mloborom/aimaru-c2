import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import type { ClientSummary } from '../api'

export default function Clients(){
  const { token } = useAuth()
  const [clients, setClients] = useState<ClientSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function load(){
    if (!token) return
    setLoading(true); setErr(null)
    try {
      console.log('[Clients] GET /api/clients …')
      const res = await fetch('/api/clients', {
        method: 'GET',
        cache: 'no-store',              // <- bypass browser cache
        credentials: 'include',
        headers: {
          'Accept': 'application/json',
          'Authorization': `Bearer ${token}`, // <- REQUIRED for require_role()
        },
      })
      if (!res.ok) {
        const txt = await res.text().catch(()=> '')
        console.error('[Clients] /api/clients failed:', res.status, txt)
        throw new Error(`API /api/clients failed: ${res.status}`)
      }
      const j = await res.json()
      console.log('[Clients] /api/clients response:', j)
      setClients(j.clients || [])
    } catch (e:any) {
      console.error('[Clients] load error:', e)
      setErr(e?.message || 'Failed to load clients')
    } finally {
      setLoading(false)
    }
  }

  useEffect(()=>{
    load()
    const t = setInterval(load, 5000) // refresh every 5s
    return ()=>clearInterval(t)
  }, [token])

  if (!token) return <div className="rounded-2xl p-4 glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-cyan)', color: 'var(--aimaru-cyan)'}}>Please log in.</div>

  const connected = clients.filter(c=>c.connected)
  const offline   = clients.filter(c=>!c.connected)

  const Grid = ({items}:{items:ClientSummary[]}) => (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {items.map(c=> (
        <Link to={`/clients/${encodeURIComponent(c.id)}`} key={c.id} className="rounded-xl p-3 glow-cyan transition-all hover:glow-cyan-strong" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)'}}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xl" title={(c as any).amsi_bypassed ? "AMSI Bypassed" : "AMSI Active"}>
                {(c as any).amsi_bypassed ? '🛡️💥' : '🛡️'}
              </span>
              <div className="font-medium" style={{color: 'var(--aimaru-text)'}}>{c.id}</div>
            </div>
            <span className={`text-xs ${c.connected? 'badge-online':'badge-offline'} px-2 py-1 rounded`}>{c.connected? 'connected':'offline'}</span>
          </div>
          <div className="mt-2 flex gap-3 text-xs" style={{color: 'var(--aimaru-text-dim)'}}>
            <div>Q:{c.queued}</div>
            <div>D:{c.delivered}</div>
            <div>C:{c.completed}</div>
            <div>T:{c.total}</div>
          </div>
          {c.last_seen_at && <div className="mt-1 text-[11px]" style={{color: 'var(--aimaru-text-dim)'}}>last seen {new Date(c.last_seen_at).toLocaleString()}</div>}
        </Link>
      ))}
      {items.length===0 && <div style={{color: 'var(--aimaru-text-dim)'}}>None</div>}
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-xl font-semibold glow-text-cyan" style={{color: 'var(--aimaru-cyan)'}}>Clients</h2>
        <button className="ml-auto rounded-lg px-3 py-1 glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-cyan)', color: 'var(--aimaru-cyan)'}} onClick={load} disabled={loading}>
          {loading?'…':'Refresh'}
        </button>
      </div>

      {err && (
        <div className="rounded-xl p-3" style={{background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #EF4444', color: '#EF4444'}}>
          {err}
        </div>
      )}

      <section className="rounded-2xl p-4 glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)'}}>
        <div className="font-semibold mb-2" style={{color: 'var(--aimaru-cyan)'}}>Connected</div>
        <Grid items={connected}/>
      </section>

      <section className="rounded-2xl p-4 glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)'}}>
        <div className="font-semibold mb-2" style={{color: 'var(--aimaru-cyan)'}}>Offline</div>
        <Grid items={offline}/>
      </section>
    </div>
  )
}
