// ui-app/src/components/AMSIDeployment.tsx
import React, { useState, useEffect } from 'react'
import { useAuth } from '../auth/AuthContext'

interface AMSIDeploymentConfig {
  obfuscation_level: 'base64' | 'advanced' | 'elite'
  var_prefix: string
  function_prefix: string
  patch_etw: boolean
  enable_verbose: boolean
}

interface Client {
  id: string
  connected: boolean
  last_seen_at: string | null
  queued: number
  delivered: number
  completed: number
  total: number
  amsi_bypassed: boolean
}

interface AMSIScriptPreview {
  success: boolean
  obfuscation_level: string
  script_content: string
  script_size_bytes: number
  script_size_kb: number
  variable_mappings: Record<string, string>
  function_mappings: Record<string, string>
}

interface AMSIDeploymentResult {
  success: boolean
  client_id: string
  obfuscation_level: string
  script_size_bytes: number
  script_preview: string
  instruction_id?: string
  timestamp: string
  message: string
}

interface InstructionResult {
  id: string
  client_id: string
  command: string
  status: string
  result_plain?: string
  created_at: string
  delivered_at?: string
  completed_at?: string
}

export default function AMSIDeployment() {
  const { token } = useAuth()

  const [config, setConfig] = useState<AMSIDeploymentConfig>({
    obfuscation_level: 'advanced',
    var_prefix: 'amsi',
    function_prefix: 'Invoke',
    patch_etw: false,
    enable_verbose: false
  })

  const [selectedClient, setSelectedClient] = useState<string>('')
  const [clients, setClients] = useState<Client[]>([])
  const [preview, setPreview] = useState<AMSIScriptPreview | null>(null)
  const [deploymentResult, setDeploymentResult] = useState<AMSIDeploymentResult | null>(null)
  const [executionResult, setExecutionResult] = useState<InstructionResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [checkingResult, setCheckingResult] = useState(false)

  useEffect(() => {
    if (token) {
      loadClients()
    }
  }, [token])

  const loadClients = async () => {
    try {
      const response = await fetch('/api/clients', {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })

      if (response.ok) {
        const data = await response.json()
        setClients(data.clients || [])
      }
    } catch (error) {
      console.error('Failed to load clients:', error)
    }
  }

  const previewScript = async () => {
    setPreviewLoading(true)

    try {
      const response = await fetch('/api/amsi-deployment/preview', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ config })
      })

      if (response.ok) {
        const data = await response.json()
        setPreview(data)
      } else {
        const error = await response.json()
        alert(`Preview failed: ${error.detail}`)
      }
    } catch (error: any) {
      console.error('Preview failed:', error)
      alert(`Preview failed: ${error.message}`)
    } finally {
      setPreviewLoading(false)
    }
  }

  const deployScript = async () => {
    if (!selectedClient) {
      alert('Please select a client first')
      return
    }

    setLoading(true)
    setDeploymentResult(null)
    setExecutionResult(null)

    try {
      const response = await fetch('/api/amsi-deployment/deploy', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          client_id: selectedClient,
          config
        })
      })

      if (response.ok) {
        const data = await response.json()
        setDeploymentResult(data)
      } else {
        const error = await response.json()
        alert(`Deployment failed: ${error.detail}`)
      }
    } catch (error: any) {
      console.error('Deployment failed:', error)
      alert(`Deployment failed: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const checkExecutionResult = async () => {
    if (!deploymentResult?.instruction_id) {
      alert('No instruction ID available')
      return
    }

    setCheckingResult(true)

    try {
      const response = await fetch(`/api/results/${deploymentResult.instruction_id}?plaintext=true`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      })

      if (response.ok) {
        const data = await response.json()
        setExecutionResult(data)
      } else {
        const error = await response.json()
        alert(`Failed to fetch result: ${error.detail}`)
      }
    } catch (error: any) {
      console.error('Failed to fetch result:', error)
      alert(`Failed to fetch result: ${error.message}`)
    } finally {
      setCheckingResult(false)
    }
  }

  const downloadScript = () => {
    if (!preview) return

    const blob = new Blob([preview.script_content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `amsi-bypass-${config.obfuscation_level}-${Date.now()}.ps1`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const copyScript = () => {
    if (!preview) return

    navigator.clipboard.writeText(preview.script_content)
    alert('Script copied to clipboard!')
  }

  if (!token) {
    return (
      <div className="rounded-xl p-6" style={{
        background: 'rgba(245, 158, 11, 0.1)',
        border: '1px solid #F59E0B',
        color: '#F59E0B'
      }}>
        <div className="text-center">
          <div className="text-4xl mb-4">🔒</div>
          <h3 className="text-lg font-medium mb-2" style={{ color: 'var(--aimaru-cyan)' }}>
            AUTHENTICATION REQUIRED
          </h3>
          <p style={{ color: 'var(--aimaru-text)' }}>Please log in to access AMSI Deployment.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="rounded-xl p-6" style={{
        background: 'linear-gradient(to right, #DC2626, #EF4444)',
        boxShadow: '0 0 30px rgba(220, 38, 38, 0.3)'
      }}>
        <h1 className="text-2xl font-bold mb-2 uppercase tracking-wide" style={{ color: '#FFF' }}>
          🛡️ AMSI BYPASS DEPLOYMENT
        </h1>
        <p className="opacity-90" style={{ color: '#FFF' }}>
          Deploy obfuscated AMSI bypass scripts to MCP clients with multi-level obfuscation
        </p>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Configuration Panel */}
        <div className="space-y-6">
          {/* Obfuscation Settings */}
          <div className="rounded-xl shadow-sm border p-6" style={{
            background: 'var(--aimaru-dark-card)',
            borderColor: 'var(--aimaru-dark-border)'
          }}>
            <h2 className="text-lg font-semibold mb-4">🔐 Obfuscation Settings</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Obfuscation Level</label>
                <select
                  value={config.obfuscation_level}
                  onChange={(e) => setConfig(prev => ({ ...prev, obfuscation_level: e.target.value as any }))}
                  className="w-full px-3 py-2 rounded-md focus:outline-none"
                  style={{
                    background: 'var(--aimaru-dark-surface)',
                    border: '1px solid var(--aimaru-dark-border)',
                    color: 'var(--aimaru-text)'
                  }}
                >
                  <option value="base64">Base64 - Simple Base64 encoding (Fast/Testing)</option>
                  <option value="advanced">Advanced - Character codes + chunked Base64 (Balanced)</option>
                  <option value="elite">Elite - XOR encryption + multi-layer encoding (Stealth)</option>
                </select>
                <div className="mt-2 text-xs" style={{ color: 'var(--aimaru-text-dim)' }}>
                  {config.obfuscation_level === 'base64' && '⚡ Fast execution, easily reversible, good for testing'}
                  {config.obfuscation_level === 'advanced' && '🔒 Moderate security, requires parsing and reassembly'}
                  {config.obfuscation_level === 'elite' && '🛡️ Maximum security, complex deobfuscation required'}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Variable Prefix</label>
                  <input
                    type="text"
                    value={config.var_prefix}
                    onChange={(e) => setConfig(prev => ({ ...prev, var_prefix: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md focus:outline-none"
                    style={{
                      background: 'var(--aimaru-dark-surface)',
                      border: '1px solid var(--aimaru-dark-border)',
                      color: 'var(--aimaru-text)'
                    }}
                    placeholder="amsi"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Function Prefix</label>
                  <input
                    type="text"
                    value={config.function_prefix}
                    onChange={(e) => setConfig(prev => ({ ...prev, function_prefix: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md focus:outline-none"
                    style={{
                      background: 'var(--aimaru-dark-surface)',
                      border: '1px solid var(--aimaru-dark-border)',
                      color: 'var(--aimaru-text)'
                    }}
                    placeholder="Invoke"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={config.patch_etw}
                    onChange={(e) => setConfig(prev => ({ ...prev, patch_etw: e.target.checked }))}
                    className="mr-2"
                  />
                  <span className="text-sm">Patch ETW (Event Tracing for Windows)</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={config.enable_verbose}
                    onChange={(e) => setConfig(prev => ({ ...prev, enable_verbose: e.target.checked }))}
                    className="mr-2"
                  />
                  <span className="text-sm">Enable Verbose Output</span>
                </label>
              </div>
            </div>
          </div>

          {/* Client Selection */}
          <div className="rounded-xl shadow-sm border p-6" style={{
            background: 'var(--aimaru-dark-card)',
            borderColor: 'var(--aimaru-dark-border)'
          }}>
            <h2 className="text-lg font-semibold mb-4">🎯 Target Client</h2>

            <div className="space-y-4">
              {/* Client Count Badge */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono" style={{ color: 'var(--aimaru-text-dim)' }}>
                  Available Clients:
                </span>
                <span className="px-2 py-1 rounded text-xs font-bold"
                      style={{
                        background: clients.length > 0 ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                        color: clients.length > 0 ? '#22C55E' : '#EF4444',
                        border: `1px solid ${clients.length > 0 ? '#22C55E' : '#EF4444'}`
                      }}>
                  {clients.length} CLIENT{clients.length !== 1 ? 'S' : ''}
                </span>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Select MCP Client</label>
                <select
                  value={selectedClient}
                  onChange={(e) => setSelectedClient(e.target.value)}
                  className="w-full px-3 py-2 rounded-md focus:outline-none font-mono"
                  style={{
                    background: 'var(--aimaru-dark-surface)',
                    border: '1px solid var(--aimaru-dark-border)',
                    color: 'var(--aimaru-text)'
                  }}
                  disabled={clients.length === 0}
                >
                  <option value="">
                    {clients.length === 0 ? '-- No Clients Available --' : '-- Select Client --'}
                  </option>
                  {clients.map(client => (
                    <option key={client.id} value={client.id}>
                      {client.amsi_bypassed ? '🛡️💥 ' : '🛡️ '}{client.id} [{client.connected ? 'CONNECTED' : 'OFFLINE'}]
                      {client.amsi_bypassed ? ' [AMSI BYPASSED]' : ''}
                      {client.last_seen_at ? ` - Last seen: ${new Date(client.last_seen_at).toLocaleTimeString()}` : ''}
                    </option>
                  ))}
                </select>
              </div>

              {/* No Clients Message */}
              {clients.length === 0 && (
                <div className="p-4 rounded-lg text-center"
                     style={{
                       background: 'rgba(245, 158, 11, 0.1)',
                       border: '1px solid #F59E0B'
                     }}>
                  <div className="text-2xl mb-2">⚠️</div>
                  <p className="text-sm font-medium mb-1" style={{ color: '#F59E0B' }}>
                    No MCP Clients Connected
                  </p>
                  <p className="text-xs" style={{ color: 'var(--aimaru-text-dim)' }}>
                    Deploy an MCP client using the Client Builder, or connect an existing client to begin deployment.
                  </p>
                </div>
              )}

              <button
                onClick={loadClients}
                className="w-full px-4 py-2 rounded text-sm font-bold uppercase tracking-wide transition-all"
                style={{
                  background: 'rgba(59, 130, 246, 0.2)',
                  border: '1px solid #3B82F6',
                  color: '#3B82F6'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(59, 130, 246, 0.3)'
                  e.currentTarget.style.boxShadow = '0 0 15px rgba(59, 130, 246, 0.5)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(59, 130, 246, 0.2)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                🔄 Refresh Clients
              </button>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="rounded-xl shadow-sm border p-6" style={{
            background: 'var(--aimaru-dark-card)',
            borderColor: 'var(--aimaru-dark-border)'
          }}>
            <h2 className="text-lg font-semibold mb-4">⚡ Actions</h2>

            <div className="space-y-3">
              <button
                onClick={previewScript}
                disabled={previewLoading}
                className="w-full px-4 py-2 rounded text-sm font-bold uppercase tracking-wide transition-all disabled:opacity-50"
                style={{
                  background: 'rgba(168, 85, 247, 0.2)',
                  border: '1px solid #A855F7',
                  color: '#A855F7'
                }}
                onMouseEnter={(e) => {
                  if (!previewLoading) {
                    e.currentTarget.style.background = 'rgba(168, 85, 247, 0.3)'
                    e.currentTarget.style.boxShadow = '0 0 15px rgba(168, 85, 247, 0.5)'
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(168, 85, 247, 0.2)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                {previewLoading ? '🔄 Generating...' : '👁️ Preview Script'}
              </button>

              <button
                onClick={deployScript}
                disabled={loading || !selectedClient}
                className="w-full px-4 py-2 rounded text-sm font-bold uppercase tracking-wide transition-all disabled:opacity-50"
                style={{
                  background: 'rgba(220, 38, 38, 0.2)',
                  border: '1px solid #DC2626',
                  color: '#DC2626'
                }}
                onMouseEnter={(e) => {
                  if (!loading && selectedClient) {
                    e.currentTarget.style.background = 'rgba(220, 38, 38, 0.3)'
                    e.currentTarget.style.boxShadow = '0 0 15px rgba(220, 38, 38, 0.5)'
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(220, 38, 38, 0.2)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                {loading ? '🚀 Deploying...' : '🚀 Deploy to Client'}
              </button>
            </div>
          </div>
        </div>

        {/* Preview/Result Panel */}
        <div className="space-y-6">
          {/* Script Preview */}
          {preview && (
            <div className="rounded-xl shadow-sm border p-6" style={{
              background: 'var(--aimaru-dark-card)',
              borderColor: 'var(--aimaru-dark-border)'
            }}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">📄 Script Preview</h2>
                <div className="flex gap-2">
                  <span className="px-2 py-1 bg-purple-100 text-purple-800 rounded text-xs font-medium">
                    {preview.obfuscation_level.toUpperCase()}
                  </span>
                  <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                    {preview.script_size_kb} KB
                  </span>
                </div>
              </div>

              <div className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto max-h-96 font-mono text-xs">
                <pre className="whitespace-pre-wrap">{preview.script_content.substring(0, 1500)}</pre>
                {preview.script_content.length > 1500 && (
                  <div className="text-gray-500 mt-2">
                    ... ({preview.script_content.length - 1500} more characters) ...
                  </div>
                )}
              </div>

              <div className="mt-4 flex gap-2">
                <button
                  onClick={downloadScript}
                  className="px-3 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600"
                >
                  📥 Download
                </button>
                <button
                  onClick={copyScript}
                  className="px-3 py-1 bg-gray-600 text-white rounded text-sm hover:bg-gray-700"
                >
                  📋 Copy
                </button>
              </div>
            </div>
          )}

          {/* Deployment Result */}
          {deploymentResult && (
            <div className={`rounded-xl shadow-sm border p-6 ${
              deploymentResult.success
                ? 'bg-green-50 border-green-200'
                : 'bg-red-50 border-red-200'
            }`}>
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                {deploymentResult.success ? '✅' : '❌'} Deployment Result
              </h2>

              <div className="space-y-2 text-sm">
                <div><strong>Client ID:</strong> {deploymentResult.client_id}</div>
                <div><strong>Obfuscation:</strong> {deploymentResult.obfuscation_level.toUpperCase()}</div>
                <div><strong>Script Size:</strong> {(deploymentResult.script_size_bytes / 1024).toFixed(2)} KB</div>
                {deploymentResult.instruction_id && (
                  <div><strong>Instruction ID:</strong> {deploymentResult.instruction_id}</div>
                )}
                <div><strong>Timestamp:</strong> {new Date(deploymentResult.timestamp).toLocaleString()}</div>
                <div className="mt-4 p-3 bg-white rounded text-gray-800">
                  {deploymentResult.message}
                </div>
              </div>

              {deploymentResult.instruction_id && (
                <div className="mt-4">
                  <button
                    onClick={checkExecutionResult}
                    disabled={checkingResult}
                    className="w-full px-4 py-2 rounded text-sm font-bold uppercase tracking-wide transition-all disabled:opacity-50"
                    style={{
                      background: 'rgba(34, 197, 94, 0.2)',
                      border: '1px solid #22C55E',
                      color: '#22C55E'
                    }}
                    onMouseEnter={(e) => {
                      if (!checkingResult) {
                        e.currentTarget.style.background = 'rgba(34, 197, 94, 0.3)'
                        e.currentTarget.style.boxShadow = '0 0 15px rgba(34, 197, 94, 0.5)'
                      }
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'rgba(34, 197, 94, 0.2)'
                      e.currentTarget.style.boxShadow = 'none'
                    }}
                  >
                    {checkingResult ? '🔄 Checking...' : '📊 Check Execution Result'}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Execution Result */}
          {executionResult && (
            <div className="rounded-xl shadow-sm border p-6" style={{
              background: 'var(--aimaru-dark-card)',
              borderColor: executionResult.status === 'completed' ? '#22C55E' : '#F59E0B'
            }}>
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                {executionResult.status === 'completed' ? '✅' : '⏳'} Execution Result
              </h2>

              <div className="space-y-3 text-sm">
                <div className="flex justify-between items-center">
                  <strong>Status:</strong>
                  <span className="px-2 py-1 rounded text-xs font-bold uppercase"
                        style={{
                          background: executionResult.status === 'completed' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                          color: executionResult.status === 'completed' ? '#22C55E' : '#F59E0B',
                          border: `1px solid ${executionResult.status === 'completed' ? '#22C55E' : '#F59E0B'}`
                        }}>
                    {executionResult.status}
                  </span>
                </div>

                <div><strong>Instruction ID:</strong> <code className="font-mono text-xs">{executionResult.id}</code></div>
                <div><strong>Client:</strong> {executionResult.client_id}</div>

                {executionResult.created_at && (
                  <div><strong>Created:</strong> {new Date(executionResult.created_at).toLocaleString()}</div>
                )}
                {executionResult.delivered_at && (
                  <div><strong>Delivered:</strong> {new Date(executionResult.delivered_at).toLocaleString()}</div>
                )}
                {executionResult.completed_at && (
                  <div><strong>Completed:</strong> {new Date(executionResult.completed_at).toLocaleString()}</div>
                )}

                {executionResult.result_plain && (
                  <div className="mt-4">
                    <strong className="block mb-2">PowerShell Output:</strong>
                    <div className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto max-h-96 font-mono text-xs">
                      <pre className="whitespace-pre-wrap">{executionResult.result_plain}</pre>
                    </div>
                  </div>
                )}

                {executionResult.status !== 'completed' && (
                  <div className="mt-4 p-3 rounded-lg text-center"
                       style={{
                         background: 'rgba(245, 158, 11, 0.1)',
                         border: '1px solid #F59E0B'
                       }}>
                    <p className="text-sm" style={{ color: '#F59E0B' }}>
                      ⏳ Script is {executionResult.status}. The client needs to execute it and return results.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Information Card */}
          <div className="rounded-xl shadow-sm border p-6" style={{
            background: 'rgba(59, 130, 246, 0.1)',
            borderColor: '#3B82F6'
          }}>
            <h3 className="font-semibold mb-2 flex items-center gap-2" style={{ color: '#3B82F6' }}>
              ℹ️ Information
            </h3>
            <div className="text-sm space-y-1" style={{ color: 'var(--aimaru-text)' }}>
              <p>• AMSI bypass uses memory patching techniques</p>
              <p>• Each script is uniquely obfuscated per deployment</p>
              <p>• ETW patching disables Event Tracing telemetry</p>
              <p>• Test in controlled environments before production use</p>
              <p>• Higher obfuscation levels increase detection evasion</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
