import React, { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import type { LlmProviderMeta } from '../api'

type Cfg = {
  id: string;
  name: string;
  provider: string;
  model: string;
  base_url?: string;
  temperature: number;
  is_active: boolean;
  created_at?: string;
  owner_user_id?: string;
}

type EditingConfig = Cfg & {
  api_key?: string;
  isEditing: boolean;
}

export default function LLM(){
  const { token, api } = useAuth()
  const [rows, setRows] = useState<Cfg[]>([])
  const [editingRows, setEditingRows] = useState<Record<string, EditingConfig>>({})
  const [providers, setProviders] = useState<Record<string, LlmProviderMeta>>({})
  const [form, setForm] = useState({
    name: '',
    provider: 'openai',
    model: 'gpt-4o-mini',
    api_key: '',
    base_url: '',
    temperature: 0.2
  })
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [showDetails, setShowDetails] = useState<Record<string, boolean>>({})

  async function load(){
    if (!token) return
    setLoading(true); setErr('')
    try { 
      const j = await api.llmConfigs()
      const configs = Array.isArray(j) ? j : (j?.configs || [])
      setRows(configs)
      // Clear any editing states for configs that no longer exist
      setEditingRows(prev => {
        const newState = { ...prev }
        Object.keys(newState).forEach(id => {
          if (!configs.find(c => c.id === id)) {
            delete newState[id]
          }
        })
        return newState
      })
    }
    catch(e:any){ setErr(e.message||'Failed to load') }
    finally { setLoading(false) }
  }
  
  useEffect(() => {
    load()
    if (token) {
      api.llmProviders().then(setProviders).catch(() => {})
    }
  }, [token])

  const activeCount = useMemo(()=> rows.filter(r=>r.is_active).length, [rows])

  async function onCreate(e: React.FormEvent){
    e.preventDefault()
    if (!form.name || !form.provider || !form.model || !form.api_key) { 
      setErr('All fields are required'); return 
    }
    
    if (form.temperature < 0 || form.temperature > 2) {
      setErr('Temperature must be between 0 and 2'); return
    }
    
    setLoading(true)
    setErr('')
    
    try {
      await api.llmCreate({
        ...form,
        base_url: form.base_url.trim() || undefined,
        is_active: true
      })
      setForm({
        name: '',
        provider: 'openai',
        model: 'gpt-4o-mini',
        api_key: '',
        base_url: '',
        temperature: 0.2
      })
      await load()
    }
    catch(e:any){ setErr(e.message||'Create failed') }
    finally { setLoading(false) }
  }

  function startEdit(config: Cfg) {
    setEditingRows(prev => ({
      ...prev,
      [config.id]: {
        ...config,
        api_key: '', // Don't show existing key for security
        isEditing: true
      }
    }))
    setErr('') // Clear any previous errors
  }

  function cancelEdit(id: string) {
    setEditingRows(prev => {
      const newState = { ...prev }
      delete newState[id]
      return newState
    })
  }

  async function saveEdit(id: string) {
    const editConfig = editingRows[id]
    if (!editConfig) return

    if (!editConfig.name || !editConfig.provider || !editConfig.model) {
      setErr('Name, provider, and model are required')
      return
    }

    if (editConfig.temperature < 0 || editConfig.temperature > 2) {
      setErr('Temperature must be between 0 and 2')
      return
    }

    try {
      setLoading(true)
      await api.llmUpdate(id, {
        name: editConfig.name,
        provider: editConfig.provider,
        model: editConfig.model,
        temperature: editConfig.temperature,
        base_url: editConfig.base_url?.trim() || undefined,
        ...(editConfig.api_key && { api_key: editConfig.api_key })
      })
      
      cancelEdit(id)
      await load()
      setErr('')
    } catch(e: any) {
      setErr(`Update failed: ${e.message || e}`)
    } finally {
      setLoading(false)
    }
  }

  function updateEditField(id: string, field: keyof EditingConfig, value: any) {
    setEditingRows(prev => ({
      ...prev,
      [id]: {
        ...prev[id],
        [field]: value
      }
    }))
  }

  async function toggleActive(r: Cfg){
    try {
      await api.llmActivate(r.id, !r.is_active)
      setRows(rows.map(x => x.id===r.id ? { ...x, is_active: !x.is_active } : x))
    } catch(e:any){ 
      setErr(`Toggle failed: ${e.message||e}`)
    }
  }

  async function safeDelete(r: Cfg){
    if (r.is_active){
      const ok = confirm(`⚠️ Delete API Key: "${r.name}"\n\nThis API key is currently active.\n\nDo you want to deactivate and delete this API key?`)
      if (!ok) return
      try { 
        await api.llmActivate(r.id, false)
        r.is_active = false 
      }
      catch(e:any){ 
        setErr(`Deactivate failed: ${e.message||e}`)
        return 
      }
    }

    try {
      await api.llmDelete(r.id)
      setRows(rows.filter(x => x.id !== r.id))
      return
    } catch(e:any){
      const msg = String(e.message||'')
      if (!msg.startsWith('409')) { 
        setErr(`Delete failed: ${msg}`)
        return 
      }
    }

    // Handle 409: still referenced
    let usage = 0
    try { 
      const u = await api.llmUsage(r.id)
      usage = (u && typeof u.sessions_using==='number') ? u.sessions_using : 0 
    } catch {}
    
    const doDetach = confirm(
      usage > 0
        ? `⚠️ Delete API Key: "${r.name}"\n\nThis API key is currently used by ${usage} chat session(s).\n\nThese sessions will be detached from this configuration.\n\nAre you sure you want to delete this API key?`
        : `⚠️ Delete API Key: "${r.name}"\n\nThis API key is referenced by existing chat sessions.\n\nThese sessions will be detached from this configuration.\n\nAre you sure you want to delete this API key?`
    )
    if (!doDetach) return

    try { 
      await api.llmDetachSessions(r.id) 
    }
    catch(e:any){
      setErr(`Cannot detach automatically: ${e.message||e}\n` +
            `Please reassign or delete sessions manually, then retry.`)
      return
    }

    try {
      await api.llmDelete(r.id)
      setRows(rows.filter(x => x.id !== r.id))
    } catch(e:any){ 
      setErr(`Delete still failed: ${e.message||e}`) 
    }
  }

  function toggleDetails(id: string) {
    setShowDetails(prev => ({
      ...prev,
      [id]: !prev[id]
    }))
  }

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'Unknown'
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const maskApiKey = (provider: string) => {
    switch(provider) {
      case 'openai':    return 'sk-...••••••••••••••••••••••••••••••••••••••••••••••••'
      case 'anthropic': return 'sk-ant-...••••••••••••••••••••••••••••••••••••••••••'
      case 'zhipu':     return 'sk-...••••••••••••••••••••••••••••••••••••••••••••••••'
      default:          return '••••••••••••••••••••••••••••••••••••••••••••••••••••••'
    }
  }

  if (!token) {
    return (
      <div style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-cyan)', color: 'var(--aimaru-cyan)'}} className="rounded-2xl p-4 glow-cyan">
        Please log in to manage LLM configurations.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold glow-text-cyan" style={{color: 'var(--aimaru-cyan)'}}>LLM API Configurations</h2>
          <p className="text-sm mt-1" style={{color: 'var(--aimaru-text-dim)'}}>Manage API keys and settings for AI chat functionality</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-sm" style={{color: 'var(--aimaru-text-dim)'}}>
            Active: <span className="font-semibold" style={{color: 'var(--aimaru-cyan)'}}>{activeCount}</span> / {rows.length}
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="text-sm disabled:opacity-50 flex items-center gap-1 glow-cyan rounded-lg px-3 py-1"
            style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-cyan)', color: 'var(--aimaru-cyan)'}}
          >
            <span>{loading ? 'Loading...' : '🔄 Refresh'}</span>
          </button>
        </div>
      </div>

      {/* Error Display */}
      {err && (
        <div className="rounded-xl p-4" style={{background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #EF4444', color: '#EF4444'}}>
          <div className="flex items-start">
            <span className="mr-2 mt-0.5">⚠️</span>
            <div className="flex-1">
              <div className="font-medium">Error</div>
              <div className="text-sm mt-1 whitespace-pre-line">{err}</div>
            </div>
            <button
              onClick={() => setErr('')}
              className="ml-2 hover:opacity-70"
              style={{color: '#EF4444'}}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Create Form */}
      <form className="rounded-2xl p-6 space-y-4 glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)'}} onSubmit={onCreate}>
        <h3 className="text-lg font-medium glow-text-cyan" style={{color: 'var(--aimaru-cyan)'}}>Add New Configuration</h3>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>Name</label>
            <input
              className="w-full rounded-lg px-3 py-2"
              placeholder="My OpenAI Key"
              value={form.name}
              onChange={e=>setForm(s=>({...s, name:e.target.value}))}
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>Provider</label>
            <select
              className="w-full rounded-lg px-3 py-2"
              value={form.provider}
              onChange={e => setForm(s => ({ ...s, provider: e.target.value, model: providers[e.target.value]?.models[0] || '', base_url: '' }))}
            >
              {Object.entries(providers).length > 0
                ? Object.entries(providers).map(([key, meta]) => (
                    <option key={key} value={key}>{meta.display}</option>
                  ))
                : <>
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="zhipu">Zhipu AI (GLM)</option>
                  </>
              }
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>Model</label>
            <select
              className="w-full rounded-lg px-3 py-2"
              style={{background: 'var(--aimaru-dark-input-bg, #1a1a1a)', color: 'var(--aimaru-text)'}}
              value={form.model}
              onChange={e=>setForm(s=>({...s, model:e.target.value}))}
            >
              <option value="">-- Select a model --</option>
              {providers[form.provider]?.models?.map(m => (
                <option key={m} value={m}>{m}</option>
              ))}
              <option value="" disabled>────────────────</option>
              <option value="custom">Custom / Other Model</option>
            </select>
            {form.model === 'custom' && (
              <input
                className="w-full rounded-lg px-3 py-2 mt-2"
                placeholder="Enter custom model name"
                value={form.model !== 'custom' ? form.model : ''}
                onChange={e=>setForm(s=>({...s, model:e.target.value}))}
              />
            )}
          </div>

          <div>
            <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>Temperature</label>
            <input
              type="number"
              min="0"
              max="2"
              step="0.1"
              className="w-full rounded-lg px-3 py-2"
              value={form.temperature}
              onChange={e=>setForm(s=>({...s, temperature:parseFloat(e.target.value) || 0}))}
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>API Key</label>
          <input
            className="w-full rounded-lg px-3 py-2"
            type="password"
            placeholder="sk-..."
            value={form.api_key}
            onChange={e=>setForm(s=>({...s, api_key:e.target.value}))}
          />
          <div className="text-xs mt-1" style={{color: 'var(--aimaru-text-dim)'}}>
            Stored encrypted — never exposed in plaintext
          </div>
        </div>

        {providers[form.provider]?.default_base_url !== undefined && (
          <div>
            <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>
              Base URL
              <span className="ml-2 text-xs font-normal" style={{color: 'var(--aimaru-text-dim)'}}>
                (pre-filled from provider default — override if needed)
              </span>
            </label>
            <input
              className="w-full rounded-lg px-3 py-2 font-mono text-sm"
              placeholder={providers[form.provider].default_base_url || 'https://api.openai.com/v1'}
              value={form.base_url || providers[form.provider].default_base_url || ''}
              onChange={e=>setForm(s=>({...s, base_url:e.target.value}))}
            />
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="px-6 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-all hover:glow-cyan-strong"
          style={{background: 'var(--aimaru-cyan)', color: 'var(--aimaru-dark-bg)', fontWeight: 'bold'}}
        >
          {loading ? 'Adding...' : 'Add Configuration'}
        </button>
      </form>

      {/* Configurations List */}
      <div className="rounded-2xl overflow-hidden glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)'}}>
        <div className="px-6 py-4" style={{borderBottom: '1px solid var(--aimaru-dark-border)'}}>
          <h3 className="text-lg font-medium glow-text-cyan" style={{color: 'var(--aimaru-cyan)'}}>Existing Configurations</h3>
        </div>

        <div style={{borderTop: '1px solid var(--aimaru-dark-border)'}}>
          {rows.map(r => {
            const editing = editingRows[r.id]
            const showingDetails = showDetails[r.id]
            
            return (
              <div key={r.id} className="p-6" style={{borderBottom: '1px solid var(--aimaru-dark-border)'}}>
                {editing ? (
                  // Edit Mode
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h4 className="font-medium" style={{color: 'var(--aimaru-cyan)'}}>Edit Configuration</h4>
                      <div className="flex gap-2">
                        <button
                          onClick={() => saveEdit(r.id)}
                          disabled={loading}
                          className="px-3 py-1 rounded text-sm disabled:opacity-50 hover:glow-cyan"
                          style={{background: '#10B981', color: 'white'}}
                        >
                          Save
                        </button>
                        <button
                          onClick={() => cancelEdit(r.id)}
                          className="px-3 py-1 rounded text-sm hover:opacity-80"
                          style={{background: 'var(--aimaru-gray)', color: 'var(--aimaru-text)'}}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>

                    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                      <div>
                        <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>Name</label>
                        <input
                          className="w-full rounded px-3 py-2"
                          value={editing.name}
                          onChange={e => updateEditField(r.id, 'name', e.target.value)}
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>Provider</label>
                        <select
                          className="w-full rounded px-3 py-2"
                          value={editing.provider}
                          onChange={e => updateEditField(r.id, 'provider', e.target.value)}
                        >
                          {Object.entries(providers).length > 0
                            ? Object.entries(providers).map(([key, meta]) => (
                                <option key={key} value={key}>{meta.display}</option>
                              ))
                            : <>
                                <option value="openai">OpenAI</option>
                                <option value="anthropic">Anthropic (Claude)</option>
                                <option value="zhipu">Zhipu AI (GLM)</option>
                              </>
                          }
                        </select>
                      </div>

                      <div>
                        <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>Model</label>
                        <input
                          className="w-full rounded px-3 py-2"
                          value={editing.model}
                          onChange={e => updateEditField(r.id, 'model', e.target.value)}
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>Temperature</label>
                        <input
                          type="number"
                          min="0"
                          max="2"
                          step="0.1"
                          className="w-full rounded px-3 py-2"
                          value={editing.temperature}
                          onChange={e => updateEditField(r.id, 'temperature', parseFloat(e.target.value) || 0)}
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>
                        API Key <span style={{color: 'var(--aimaru-text-dim)'}}>(leave empty to keep current key)</span>
                      </label>
                      <input
                        type="password"
                        className="w-full rounded px-3 py-2"
                        placeholder="Enter new API key (optional)"
                        value={editing.api_key || ''}
                        onChange={e => updateEditField(r.id, 'api_key', e.target.value)}
                      />
                    </div>

                    {providers[editing.provider]?.default_base_url !== undefined && (
                      <div>
                        <label className="block text-sm font-medium mb-1" style={{color: 'var(--aimaru-text)'}}>
                          Base URL
                          <span className="ml-2 text-xs font-normal" style={{color: 'var(--aimaru-text-dim)'}}>
                            (override endpoint URL)
                          </span>
                        </label>
                        <input
                          className="w-full rounded px-3 py-2 font-mono text-sm"
                          placeholder={providers[editing.provider].default_base_url || ''}
                          value={editing.base_url || providers[editing.provider]?.default_base_url || ''}
                          onChange={e => updateEditField(r.id, 'base_url', e.target.value)}
                        />
                      </div>
                    )}
                  </div>
                ) : (
                  // View Mode
                  <div>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div>
                          <h4 className="font-medium" style={{color: 'var(--aimaru-text)'}}>{r.name}</h4>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-sm capitalize" style={{color: 'var(--aimaru-text-dim)'}}>{r.provider}</span>
                            <span style={{color: 'var(--aimaru-dark-border)'}}>•</span>
                            <span className="text-sm font-mono" style={{color: 'var(--aimaru-text-dim)'}}>{r.model}</span>
                            <span style={{color: 'var(--aimaru-dark-border)'}}>•</span>
                            <span className="text-sm" style={{color: 'var(--aimaru-text-dim)'}}>temp: {r.temperature}</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          <label className="inline-flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={r.is_active}
                              onChange={()=>toggleActive(r)}
                              className="w-4 h-4 rounded"
                              style={{accentColor: 'var(--aimaru-cyan)'}}
                            />
                            <span className={`text-xs font-medium px-2 py-1 rounded-full ${
                              r.is_active
                                ? 'badge-online'
                                : 'badge-offline'
                            }`}>
                              {r.is_active ? 'Active' : 'Inactive'}
                            </span>
                          </label>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleDetails(r.id)}
                          className="text-sm px-2 py-1 hover:opacity-70"
                          style={{color: 'var(--aimaru-text-dim)'}}
                        >
                          {showingDetails ? '👁️ Hide' : '👁️ Details'}
                        </button>
                        <button
                          onClick={() => startEdit(r)}
                          className="text-sm px-2 py-1 hover:opacity-80"
                          style={{color: 'var(--aimaru-cyan)'}}
                        >
                          ✏️ Edit
                        </button>
                        <button
                          className="text-sm px-2 py-1 hover:opacity-80"
                          onClick={()=>safeDelete(r)}
                          style={{color: '#EF4444'}}
                        >
                          🗑️ Delete
                        </button>
                      </div>
                    </div>

                    {showingDetails && (
                      <div className="mt-4 p-4 rounded-lg" style={{background: 'var(--aimaru-dark-surface)', border: '1px solid var(--aimaru-dark-border)'}}>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                          <div>
                            <span className="font-medium" style={{color: 'var(--aimaru-text)'}}>Configuration ID:</span>
                            <div className="font-mono text-xs mt-1" style={{color: 'var(--aimaru-text-dim)'}}>{r.id}</div>
                          </div>
                          <div>
                            <span className="font-medium" style={{color: 'var(--aimaru-text)'}}>Created:</span>
                            <div className="mt-1" style={{color: 'var(--aimaru-text-dim)'}}>{formatDate(r.created_at)}</div>
                          </div>
                          <div>
                            <span className="font-medium" style={{color: 'var(--aimaru-text)'}}>API Key:</span>
                            <div className="font-mono text-xs mt-1" style={{color: 'var(--aimaru-text-dim)'}}>{maskApiKey(r.provider)}</div>
                          </div>
                          <div>
                            <span className="font-medium" style={{color: 'var(--aimaru-text)'}}>Owner:</span>
                            <div className="mt-1" style={{color: 'var(--aimaru-text-dim)'}}>{r.owner_user_id || 'System'}</div>
                          </div>
                          {r.base_url && (
                            <div className="md:col-span-2">
                              <span className="font-medium" style={{color: 'var(--aimaru-text)'}}>Base URL:</span>
                              <div className="font-mono text-xs mt-1" style={{color: 'var(--aimaru-text-dim)'}}>{r.base_url}</div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}

          {loading && (
            <div className="px-6 py-8 text-center" style={{color: 'var(--aimaru-text-dim)'}}>
              <div className="inline-flex items-center gap-2">
                <div className="cyber-loading"></div>
                Loading configurations...
              </div>
            </div>
          )}

          {rows.length === 0 && !loading && (
            <div className="px-6 py-12 text-center" style={{color: 'var(--aimaru-text-dim)'}}>
              <div className="text-4xl mb-4">🤖</div>
              <div className="font-medium text-lg" style={{color: 'var(--aimaru-text)'}}>No LLM configurations yet</div>
              <div className="text-sm mt-2">Add your first API key above to enable AI chat features</div>
              <div className="text-xs mt-2" style={{color: 'var(--aimaru-text-dim)'}}>
                Supported: OpenAI, Anthropic (Claude), Zhipu AI (GLM) — more via registry
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}