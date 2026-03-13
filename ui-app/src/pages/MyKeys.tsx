import React, { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'

type ApiKeyRow = {
  id: string
  key_id: string
  label?: string | null
  created_at?: string | null
  last_used_at?: string | null
  expires_at?: string | null
  revoked?: boolean
}

export default function MyKeys(){
  const { token, api } = useAuth()
  const [keys, setKeys] = useState<ApiKeyRow[]>([])
  const [label, setLabel] = useState('')
  const [ttl, setTtl] = useState<string>('') // minutes (optional)
  const [newToken, setNewToken] = useState<string>('') // paste-once token
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string>('')

  const canCreate = useMemo(()=>{
    if (busy) return false
    // TTL empty → ok; if present, must be positive integer
    if (ttl.trim() !== '') {
      const n = Number(ttl)
      if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) return false
    }
    return true
  }, [busy, ttl])

  async function load(){
    setErr('')
    try {
      const k = await (api as any).listApiKeys()
      setKeys(Array.isArray(k) ? k : [])
    } catch (e:any) {
      setErr(e?.message || 'Failed to load keys')
    }
  }

  useEffect(()=>{ if (token) load() },[token])

  async function create(){
    if (!canCreate) return
    setBusy(true); setErr('')
    try {
      const ttlMinutes = ttl.trim() === '' ? undefined : Number(ttl)
      const j = await (api as any).createApiKey(label.trim() || undefined, ttlMinutes)
      // Expecting server to return: { token, key: {...row...} } or at least { token }
      const tokenStr = (j && (j.token || j.api_key || j.key || j.paste_once_token)) || ''
      if (!tokenStr) throw new Error('Server did not return a token')
      setNewToken(tokenStr) // show once
      setLabel(''); setTtl('')
      await load()
    } catch (e:any) {
      setErr(e?.message || 'Failed to create API key')
    } finally {
      setBusy(false)
    }
  }

  async function revoke(id:string){
    if (!id) return
    if (!confirm('Revoke this API key? Clients using it will stop working.')) return
    setBusy(true); setErr('')
    try {
      await (api as any).revokeApiKey(id)
      await load()
    } catch (e:any) {
      setErr(e?.message || 'Failed to revoke API key')
    } finally {
      setBusy(false)
    }
  }

  function copyNewToken(){
    if (!newToken) return
    // best-effort: try clipboard, then select fallback
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(newToken)
        .catch(()=>{/* ignore */})
    }
  }

  if (!token) {
    return (
      <div className="rounded-2xl p-4 glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-cyan)', color: 'var(--aimaru-cyan)'}}>
        Please log in.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl p-4 space-y-3 glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)'}}>
        <h3 className="font-semibold glow-text-cyan" style={{color: 'var(--aimaru-cyan)'}}>Create MCP API Key</h3>
        {err && <div className="text-sm" style={{color: '#EF4444'}}>{err}</div>}

        <div className="grid sm:grid-cols-3 gap-2">
          <input
            className="rounded-xl px-3 py-2"
            placeholder="Label (optional)"
            value={label}
            onChange={e=>setLabel(e.target.value)}
            disabled={busy}
          />
          <input
            className="rounded-xl px-3 py-2"
            placeholder="TTL minutes (optional)"
            inputMode="numeric"
            value={ttl}
            onChange={e=>setTtl(e.target.value.replace(/[^\d]/g,''))}
            disabled={busy}
          />
          <button
            className={`rounded-xl px-4 py-2 transition-all ${canCreate ? 'hover:glow-cyan-strong' : 'cursor-not-allowed opacity-50'}`}
            style={canCreate ? {background: 'var(--aimaru-cyan)', color: 'var(--aimaru-dark-bg)', fontWeight: 'bold'} : {background: 'var(--aimaru-gray)', color: 'var(--aimaru-text-dim)'}}
            onClick={create}
            disabled={!canCreate}
            title={ttl && !canCreate ? 'TTL must be a positive integer in minutes' : undefined}
          >
            {busy ? 'Creating…' : 'Create'}
          </button>
        </div>

        {newToken && (
          <div className="mt-3 p-3 rounded-xl glow-cyan" style={{background: 'rgba(16, 185, 129, 0.1)', border: '1px solid #10B981'}}>
            <div className="font-medium mb-1" style={{color: '#10B981'}}>Copy your API key now (shown only once):</div>
            <pre className="text-xs p-2 rounded break-all" style={{background: 'var(--aimaru-dark-surface)', color: 'var(--aimaru-text)', border: '1px solid var(--aimaru-dark-border)'}}>{newToken}</pre>
            <div className="flex gap-2 mt-2">
              <button
                className="rounded px-3 py-1 hover:opacity-80"
                style={{background: '#10B981', color: 'white'}}
                onClick={copyNewToken}
              >
                Copy
              </button>
              <button
                className="rounded px-3 py-1 hover:opacity-80"
                style={{background: 'var(--aimaru-gray)', color: 'var(--aimaru-text)'}}
                onClick={()=>setNewToken('')}
                title="Hide token"
              >
                Hide
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-2xl p-4 overflow-auto glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)'}}>
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold glow-text-cyan" style={{color: 'var(--aimaru-cyan)'}}>Your API Keys</h3>
          <button className="rounded-lg px-3 py-1 hover:opacity-80" style={{background: 'var(--aimaru-gray)', color: 'var(--aimaru-text)'}} onClick={load} disabled={busy}>
            {busy ? '…' : 'Refresh'}
          </button>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="text-left" style={{borderBottom: '1px solid var(--aimaru-dark-border)'}}>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Key ID</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Label</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Created</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Last Used</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Expires</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Status</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {keys.map(k=> {
              const created = k.created_at ? new Date(k.created_at).toLocaleString() : ''
              const lastUsed = k.last_used_at ? new Date(k.last_used_at).toLocaleString() : '-'
              const expires = k.expires_at ? new Date(k.expires_at).toLocaleString() : '-'
              const status = k.revoked ? 'revoked' : 'active'
              return (
                <tr key={k.id} style={{borderBottom: '1px solid var(--aimaru-dark-border)'}}>
                  <td className="py-2 pr-2 font-mono text-xs" style={{color: 'var(--aimaru-text-dim)'}}>{k.key_id}</td>
                  <td className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>{k.label || '-'}</td>
                  <td className="py-2 pr-2" style={{color: 'var(--aimaru-text-dim)'}}>{created}</td>
                  <td className="py-2 pr-2" style={{color: 'var(--aimaru-text-dim)'}}>{lastUsed}</td>
                  <td className="py-2 pr-2" style={{color: 'var(--aimaru-text-dim)'}}>{expires}</td>
                  <td className="py-2 pr-2" style={{color: 'var(--aimaru-text-dim)'}}>{status}</td>
                  <td className="py-2 pr-2">
                    {!k.revoked ? (
                      <button
                        className="rounded px-2 py-1 hover:opacity-80"
                        style={{background: 'rgba(239, 68, 68, 0.2)', border: '1px solid #EF4444', color: '#EF4444'}}
                        onClick={()=>revoke(k.id)}
                        disabled={busy}
                      >
                        Revoke
                      </button>
                    ) : (
                      <span style={{color: 'var(--aimaru-text-dim)'}}>—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {keys.length === 0 && (
          <div className="mt-2" style={{color: 'var(--aimaru-text-dim)'}}>No API keys yet.</div>
        )}
      </div>

      <div className="text-xs" style={{color: 'var(--aimaru-text-dim)'}}>
        Tip: Use this API key in your MCP client, e.g.:
        <pre className="mt-1 rounded p-2 overflow-auto" style={{background: 'var(--aimaru-dark-surface)', border: '1px solid var(--aimaru-dark-border)', color: 'var(--aimaru-text)'}}>
{`.\\PSMCP.ps1 -ServerBaseUrl "https://your-api-host" -Mode Poll -ApiKey "<paste-key-here>" -SkipTlsVerify`}
        </pre>
      </div>
    </div>
  )
}

