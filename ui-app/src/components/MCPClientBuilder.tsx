// ui-app/src/components/MCPClientBuilder.tsx
import React, { useState, useEffect, useMemo } from 'react'
import { useAuth } from '../auth/AuthContext'

interface BuildConfig {
  client_id_prefix: string
  var_prefix: string
  function_prefix: string
  crypto_prefix: string
  interval_seconds: number
  skip_tls_verify: boolean
  debug_mode: boolean
  custom_user_agent: string
  obfuscation_level: 'base64' | 'advanced' | 'elite'
  compression_level: number
}

interface ClientBuildRequest {
  server_url: string
  auth_method: 'apikey' | 'username' | 'token'
  config: BuildConfig
  additional_params?: string
  download_format: 'ps1' | 'base64' | 'exe'
}

interface GeneratedNames {
  variables: Record<string, string>
  functions: Record<string, string>
  constants: Record<string, string>
}

interface ClientBuildResponse {
  success: boolean
  script_content: string
  generated_names: GeneratedNames
  build_id: string
  build_timestamp: string
  stats: Record<string, any>
  deployment_commands: Record<string, string>
}

interface ConnectivityTestResult {
  success: boolean
  status_code?: number
  response_time_ms?: number
  server_reachable: boolean
  tls_valid?: boolean
  error?: string
  message: string
  details?: string
}

// Extended API class with client builder methods
class ClientBuilderAPI {
  private baseUrl: string
  private getToken: () => string | null

  constructor(baseUrl: string, getToken: () => string | null) {
    this.baseUrl = baseUrl
    this.getToken = getToken
  }

  private async call(path: string, init?: RequestInit) {
    const url = `${this.baseUrl}${path}`
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(init?.headers as any),
    }

    const token = this.getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`

    const response = await fetch(url, { ...init, headers })
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`)
    }

    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      return response.json()
    }
    return response.text()
  }

  async generateClient(request: ClientBuildRequest): Promise<ClientBuildResponse> {
    return this.call('/api/client-builder/generate', {
      method: 'POST',
      body: JSON.stringify(request)
    })
  }

  async getBuildPresets(): Promise<Record<string, BuildConfig>> {
    const response = await this.call('/api/client-builder/presets')
    return response.presets || {}
  }

  async testServerConnectivity(serverUrl: string, skipTls: boolean = false): Promise<ConnectivityTestResult> {
    return this.call('/api/client-builder/test-connectivity', {
      method: 'POST',
      body: JSON.stringify({
        server_url: serverUrl,
        skip_tls: skipTls
      })
    })
  }

  async getTemplateFragments(): Promise<any> {
    return this.call('/api/client-builder/templates')
  }

  async getCompilationInstructions(scriptContent: string, outputName: string): Promise<any> {
    return this.call('/api/client-builder/compile-to-exe', {
      method: 'POST',
      body: JSON.stringify({
        script_content: scriptContent,
        output_name: outputName
      })
    })
  }

  async generateRandomNames(config: Partial<BuildConfig>): Promise<any> {
    return this.call('/api/client-builder/generate-random-names', {
      method: 'POST',
      body: JSON.stringify(config)
    })
  }
}

export default function MCPClientBuilder() {
  const { token } = useAuth()

  const [config, setConfig] = useState<BuildConfig>({
    client_id_prefix: 'WS',
    var_prefix: 'sys',
    function_prefix: 'Invoke',
    crypto_prefix: 'Sec',
    interval_seconds: 10,
    skip_tls_verify: false,
    debug_mode: false,
    custom_user_agent: 'PowerShell/1.0',
    obfuscation_level: 'advanced',
    compression_level: 5
  })

  const [serverUrl, setServerUrl] = useState(window.location.origin)
  const [authMethod, setAuthMethod] = useState<'apikey' | 'username' | 'token'>('apikey')
  const [additionalParams, setAdditionalParams] = useState('')
  const [generatedScript, setGeneratedScript] = useState('')
  const [building, setBuilding] = useState(false)
  const [downloadFormat, setDownloadFormat] = useState<'ps1' | 'base64' | 'exe'>('ps1')
  const [buildResult, setBuildResult] = useState<ClientBuildResponse | null>(null)
  const [presets, setPresets] = useState<Record<string, BuildConfig>>({})
  const [selectedPreset, setSelectedPreset] = useState<string>('')
  const [connectivityTest, setConnectivityTest] = useState<ConnectivityTestResult | null>(null)
  const [testingConnectivity, setTestingConnectivity] = useState(false)
  const [templateFragments, setTemplateFragments] = useState<any>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [compilationInstructions, setCompilationInstructions] = useState<any>(null)
  const [generatingNames, setGeneratingNames] = useState(false)
  const [apiGeneratedNames, setApiGeneratedNames] = useState<GeneratedNames | null>(null)

  // Initialize API client
  const clientBuilderAPI = useMemo(() => {
    return new ClientBuilderAPI('', () => token)
  }, [token])

  // Generate obfuscated names preview
  const generatedNames = useMemo<GeneratedNames>(() => {
    const generateHash = (base: string) => {
      let hash = 0
      for (let i = 0; i < base.length; i++) {
        const char = base.charCodeAt(i)
        hash = ((hash << 5) - hash) + char
        hash = hash & hash
      }
      return Math.abs(hash) % 1000
    }

    const generateName = (base: string, prefix: string, suffix: string = '') => {
      const num = generateHash(base + config.var_prefix + config.obfuscation_level)
      return `${prefix}${num}${suffix}`
    }

    return {
      variables: {
        'CRYPTO': `$script:${generateName('crypto', config.crypto_prefix)}`,
        'AuthHeader': `$script:${generateName('auth', config.var_prefix)}Hdr`,
        'AuthMethod': `$script:${generateName('method', config.var_prefix)}Mth`,
        'ServerBaseUrl': `$${generateName('server', config.var_prefix)}Base`,
        'ClientId': `$${generateName('client', config.var_prefix)}Id`,
        'IntervalSec': `$${generateName('interval', config.var_prefix)}Int`,
        'DebugMode': `$${generateName('debug', config.var_prefix)}Dbg`
      },
      functions: {
        'Invoke-HKDF': `${config.function_prefix}-${generateName('hkdf', 'H')}`,
        'Derive-CryptoFromApiKey': `${config.function_prefix}-${generateName('derive', 'D')}`,
        'Encrypt-Text': `${config.function_prefix}-${generateName('encrypt', 'E')}`,
        'Decrypt-Text': `${config.function_prefix}-${generateName('decrypt', 'D')}`,
        'Get-HmacSignatureB64': `${config.function_prefix}-${generateName('hmac', 'H')}`,
        'Test-HmacSignatureB64': `${config.function_prefix}-${generateName('verify', 'V')}`,
        'Invoke-Api': `${config.function_prefix}-${generateName('api', 'A')}`,
        'Get-ApiToken': `${config.function_prefix}-${generateName('token', 'T')}`,
        'Invoke-Instruction': `${config.function_prefix}-${generateName('exec', 'X')}`
      },
      constants: {
        'MCPv1-salt': generateName('salt', 'S'),
        'enc': generateName('enc', 'E'),
        'mac': generateName('mac', 'M')
      }
    }
  }, [config])

  // Load presets and templates on mount
  useEffect(() => {
    if (token) {
      loadPresets()
      loadTemplateFragments()
    }
  }, [token])

  const loadPresets = async () => {
    try {
      const loadedPresets = await clientBuilderAPI.getBuildPresets()
      setPresets(loadedPresets)
    } catch (error) {
      console.error('Failed to load presets:', error)
    }
  }

  const loadTemplateFragments = async () => {
    try {
      const fragments = await clientBuilderAPI.getTemplateFragments()
      setTemplateFragments(fragments)
    } catch (error) {
      console.error('Failed to load template fragments:', error)
    }
  }

  const applyPreset = (presetName: string) => {
    if (presets[presetName]) {
      setConfig(presets[presetName])
      setSelectedPreset(presetName)
    }
  }

  const testConnectivity = async () => {
    setTestingConnectivity(true)
    setConnectivityTest(null)

    try {
      const result = await clientBuilderAPI.testServerConnectivity(serverUrl, config.skip_tls_verify)
      setConnectivityTest(result)
    } catch (error: any) {
      setConnectivityTest({
        success: false,
        server_reachable: false,
        error: error.message,
        message: 'Connectivity test failed'
      })
    } finally {
      setTestingConnectivity(false)
    }
  }

  const generateClient = async () => {
    setBuilding(true)
    setBuildResult(null)
    setGeneratedScript('')

    try {
      const request: ClientBuildRequest = {
        server_url: serverUrl,
        auth_method: authMethod,
        config: config,
        additional_params: additionalParams,
        download_format: downloadFormat
      }

      const result = await clientBuilderAPI.generateClient(request)
      setGeneratedScript(result.script_content)
      setBuildResult(result)
    } catch (error: any) {
      console.error('Client generation failed:', error)
      alert(`Client generation failed: ${error.message}`)
    } finally {
      setBuilding(false)
    }
  }

  const downloadScript = () => {
    if (!generatedScript || !buildResult) return

    const timestamp = buildResult.build_timestamp.replace(/[:.]/g, '-')
    const filename = `mcp-client-${config.obfuscation_level}-${timestamp.substring(0, 19)}`

    let content = generatedScript
    let mimeType = 'text/plain'
    let extension = 'ps1'

    switch (downloadFormat) {
      case 'ps1':
        break
      case 'base64':
        extension = 'txt'
        break
      case 'exe':
        extension = 'ps1'
        break
    }

    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${filename}.${extension}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const copyToClipboard = () => {
    if (generatedScript) {
      navigator.clipboard.writeText(generatedScript)
      alert('Script copied to clipboard!')
    }
  }

  const getCompilationInstructions = async () => {
    if (!generatedScript) return

    try {
      const instructions = await clientBuilderAPI.getCompilationInstructions(
        generatedScript,
        `mcp-client-${config.obfuscation_level}`
      )
      setCompilationInstructions(instructions)
    } catch (error: any) {
      console.error('Failed to get compilation instructions:', error)
      alert(`Failed to get compilation instructions: ${error.message}`)
    }
  }

  const generateRandomNamesFromAPI = async () => {
    setGeneratingNames(true)

    try {
      const response = await clientBuilderAPI.generateRandomNames({
        var_prefix: config.var_prefix,
        function_prefix: config.function_prefix,
        crypto_prefix: config.crypto_prefix,
        obfuscation_level: config.obfuscation_level
      })

      if (response.success && response.generated_names) {
        setApiGeneratedNames(response.generated_names)
      }
    } catch (error: any) {
      console.error('Failed to generate random names:', error)
      alert(`Failed to generate random names: ${error.message}`)
    } finally {
      setGeneratingNames(false)
    }
  }

  const StatusCard = ({ title, value, subtitle, color = 'blue' }: {
    title: string, value: number | string, subtitle?: string, color?: 'blue' | 'green' | 'red' | 'yellow' | 'purple'
  }) => {
    const colors = {
      blue: 'bg-blue-50 border-blue-200 text-blue-900',
      green: 'bg-green-50 border-green-200 text-green-900',
      red: 'bg-red-50 border-red-200 text-red-900',
      yellow: 'bg-yellow-50 border-yellow-200 text-yellow-900',
      purple: 'bg-purple-50 border-purple-200 text-purple-900'
    }

    return (
      <div className={`rounded-xl border p-4 ${colors[color]}`}>
        <div className="text-2xl font-bold">{value}</div>
        <div className="text-sm font-medium">{title}</div>
        {subtitle && <div className="text-xs opacity-75">{subtitle}</div>}
      </div>
    )
  }

  if (!token) {
    return (
      <div className="rounded-xl p-6 glow-cyan"
           style={{
             background: 'rgba(245, 158, 11, 0.1)',
             border: '1px solid #F59E0B',
             color: '#F59E0B'
           }}>
        <div className="text-center">
          <div className="text-4xl mb-4">🔒</div>
          <h3 className="text-lg font-medium mb-2 glow-text-cyan" style={{ color: 'var(--aimaru-cyan)' }}>
            AUTHENTICATION REQUIRED
          </h3>
          <p style={{ color: 'var(--aimaru-text)' }}>Please log in to access the MCP Client Builder.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="rounded-xl p-6 scan-line"
           style={{
             background: 'linear-gradient(to right, var(--aimaru-cyan), #A855F7)',
             boxShadow: '0 0 30px rgba(0, 229, 204, 0.3)'
           }}>
        <h1 className="text-2xl font-bold mb-2 glow-text-cyan uppercase tracking-wide" style={{ color: '#FFF' }}>
          🔧 MCP CLIENT BUILDER
        </h1>
        <p className="opacity-90" style={{ color: '#FFF' }}>
          Generate customized, obfuscated PowerShell MCP clients with unique variable names and enhanced security features.
        </p>
      </div>

      {/* Quick Actions Bar */}
      <div className="rounded-xl p-4"
           style={{
             background: 'var(--aimaru-dark-card)',
             border: '1px solid var(--aimaru-dark-border)',
             boxShadow: '0 0 15px rgba(0, 229, 204, 0.1)'
           }}>
        <div className="flex flex-wrap gap-3 items-center">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium uppercase tracking-wide" style={{ color: 'var(--aimaru-text)' }}>
              Quick Preset:
            </label>
            <select
              value={selectedPreset}
              onChange={(e) => applyPreset(e.target.value)}
              className="px-3 py-1 rounded text-sm focus:outline-none"
              style={{
                background: 'var(--aimaru-dark-surface)',
                border: '1px solid var(--aimaru-dark-border)',
                color: 'var(--aimaru-text)'
              }}
            >
              <option value="">Custom Configuration</option>
              {Object.keys(presets).map(preset => (
                <option key={preset} value={preset}>
                  {preset.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={testConnectivity}
            disabled={testingConnectivity}
            className="px-3 py-1 rounded text-sm font-bold uppercase tracking-wide transition-all disabled:opacity-50"
            style={{
              background: 'rgba(16, 185, 129, 0.2)',
              border: '1px solid #10B981',
              color: '#10B981'
            }}
            onMouseEnter={(e) => {
              if (!testingConnectivity) {
                e.currentTarget.style.background = 'rgba(16, 185, 129, 0.3)'
                e.currentTarget.style.boxShadow = '0 0 15px rgba(16, 185, 129, 0.5)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(16, 185, 129, 0.2)'
              e.currentTarget.style.boxShadow = 'none'
            }}
          >
            {testingConnectivity ? '🔄 Testing...' : '🔌 Test Connection'}
          </button>

          <button
            onClick={generateClient}
            disabled={building || !serverUrl}
            className="px-4 py-1 rounded text-sm font-bold uppercase tracking-wide transition-all disabled:opacity-50"
            style={{
              background: 'rgba(0, 229, 204, 0.2)',
              border: '1px solid var(--aimaru-cyan)',
              color: 'var(--aimaru-cyan)'
            }}
            onMouseEnter={(e) => {
              if (!building && serverUrl) {
                e.currentTarget.style.background = 'rgba(0, 229, 204, 0.3)'
                e.currentTarget.style.boxShadow = '0 0 20px rgba(0, 229, 204, 0.5)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(0, 229, 204, 0.2)'
              e.currentTarget.style.boxShadow = 'none'
            }}
          >
            {building ? '⏳ Building...' : '🔧 Generate Client'}
          </button>

          {generatedScript && (
            <>
              <button
                onClick={downloadScript}
                className="px-3 py-1 bg-purple-500 text-white rounded text-sm hover:bg-purple-600"
              >
                📥 Download
              </button>
              <button
                onClick={copyToClipboard}
                className="px-3 py-1 bg-[var(--aimaru-dark-surface)]0 text-white rounded text-sm hover:bg-gray-600"
              >
                📋 Copy
              </button>
            </>
          )}

          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className={`px-3 py-1 rounded text-sm transition-colors ${
              showAdvanced
                ? 'bg-orange-500 text-white'
                : 'bg-[rgba(160,174,192,0.2)] text-[var(--aimaru-text)] hover:bg-gray-300'
            }`}
          >
            ⚙️ Advanced
          </button>
        </div>

        {/* Connectivity Test Results */}
        {connectivityTest && (
          <div className={`mt-3 p-3 rounded-lg text-sm ${
            connectivityTest.success
              ? 'bg-green-50 border-[var(--aimaru-dark-border)] border-[var(--aimaru-dark-border)] green-200 text-green-800'
              : 'bg-red-50 border-[var(--aimaru-dark-border)] border-[var(--aimaru-dark-border)] red-200 text-red-800'
          }`}>
            <div className="flex items-center gap-2">
              <span>{connectivityTest.success ? '✅' : '❌'}</span>
              <span className="font-medium">{connectivityTest.message}</span>
              {connectivityTest.response_time_ms && (
                <span className="text-xs opacity-75">({connectivityTest.response_time_ms}ms)</span>
              )}
            </div>
            {connectivityTest.error && (
              <div className="text-xs mt-1 opacity-75">{connectivityTest.error}</div>
            )}
          </div>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Configuration Panel */}
        <div className="space-y-6">
          {/* Basic Configuration */}
          <div className=" rounded-xl shadow-sm border p-6">
            <h2 className="text-lg font-semibold mb-4">🛠️ Basic Configuration</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Server URL</label>
                <input
                  type="text"
                  value={serverUrl}
                  onChange={(e) => setServerUrl(e.target.value)}
                  className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                  placeholder="https://your-mcp-server.com"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Client ID Prefix</label>
                  <input
                    type="text"
                    value={config.client_id_prefix}
                    onChange={(e) => setConfig(prev => ({ ...prev, client_id_prefix: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                    placeholder="WS"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Poll Interval (sec)</label>
                  <input
                    type="number"
                    value={config.interval_seconds}
                    onChange={(e) => setConfig(prev => ({ ...prev, interval_seconds: parseInt(e.target.value) || 10 }))}
                    className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                    min="5"
                    max="300"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Authentication Method</label>
                <select
                  value={authMethod}
                  onChange={(e) => setAuthMethod(e.target.value as any)}
                  className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                >
                  <option value="apikey">API Key</option>
                  <option value="username">Username/Password</option>
                  <option value="token">Enrollment Token</option>
                </select>
              </div>
            </div>
          </div>

          {/* Obfuscation Settings */}
          <div className=" rounded-xl shadow-sm border p-6">
            <h2 className="text-lg font-semibold mb-4">🔐 Obfuscation Settings</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Obfuscation Level</label>
                <select
                  value={config.obfuscation_level}
                  onChange={(e) => setConfig(prev => ({ ...prev, obfuscation_level: e.target.value as any }))}
                  className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                >
                  <option value="base64">Base64 - Simple Base64 encoding (Development/Testing)</option>
                  <option value="advanced">Advanced - Character codes + chunked Base64 (Corporate)</option>
                  <option value="elite">Elite - XOR encryption + multi-layer encoding (Production/Stealth)</option>
                </select>
                <div className="mt-2 text-xs" style={{ color: 'var(--aimaru-text-dim)' }}>
                  {config.obfuscation_level === 'base64' && '⚡ Fast execution, easily reversible, good for testing'}
                  {config.obfuscation_level === 'advanced' && '🔒 Moderate security, requires parsing and reassembly'}
                  {config.obfuscation_level === 'elite' && '🛡️ Maximum security, complex deobfuscation required, slower execution'}
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Variable Prefix</label>
                  <input
                    type="text"
                    value={config.var_prefix}
                    onChange={(e) => setConfig(prev => ({ ...prev, var_prefix: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                    placeholder="sys"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Function Prefix</label>
                  <input
                    type="text"
                    value={config.function_prefix}
                    onChange={(e) => setConfig(prev => ({ ...prev, function_prefix: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                    placeholder="Invoke"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Crypto Prefix</label>
                  <input
                    type="text"
                    value={config.crypto_prefix}
                    onChange={(e) => setConfig(prev => ({ ...prev, crypto_prefix: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                    placeholder="Sec"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Custom User-Agent</label>
                <input
                  type="text"
                  value={config.custom_user_agent}
                  onChange={(e) => setConfig(prev => ({ ...prev, custom_user_agent: e.target.value }))}
                  className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                  placeholder="PowerShell/1.0"
                />
              </div>

              <div className="flex gap-4">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={config.skip_tls_verify}
                    onChange={(e) => setConfig(prev => ({ ...prev, skip_tls_verify: e.target.checked }))}
                    className="mr-2"
                  />
                  Skip TLS Verification
                </label>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={config.debug_mode}
                    onChange={(e) => setConfig(prev => ({ ...prev, debug_mode: e.target.checked }))}
                    className="mr-2"
                  />
                  Debug Mode
                </label>
              </div>
            </div>
          </div>

          {/* Advanced Options */}
          {showAdvanced && (
            <div className=" rounded-xl shadow-sm border p-6">
              <h2 className="text-lg font-semibold mb-4">⚙️ Advanced Options</h2>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Additional Parameters</label>
                  <textarea
                    value={additionalParams}
                    onChange={(e) => setAdditionalParams(e.target.value)}
                    className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm"
                    rows={4}
                    placeholder="# Add custom PowerShell code here&#10;# Example: $Global:CustomVar = 'value'"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Download Format</label>
                  <select
                    value={downloadFormat}
                    onChange={(e) => setDownloadFormat(e.target.value as any)}
                    className="w-full px-3 py-2 rounded-md focus:outline-none" style={{ background: "var(--aimaru-dark-surface)", border: "1px solid var(--aimaru-dark-border)", color: "var(--aimaru-text)" }}
                  >
                    <option value="ps1">PowerShell Script (.ps1)</option>
                    <option value="base64">Base64 Encoded (.txt)</option>
                    <option value="exe">Executable Wrapper (.ps1)</option>
                  </select>
                </div>

                {templateFragments && (
                  <div>
                    <label className="block text-sm font-medium mb-2">Template Fragments</label>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.keys(templateFragments.fragments || {}).map(fragment => (
                        <button
                          key={fragment}
                          onClick={() => {
                            const code = templateFragments.fragments[fragment]
                            setAdditionalParams(prev => prev + '\n\n' + code)
                          }}
                          className="px-2 py-1 bg-[rgba(160,174,192,0.1)] text-[var(--aimaru-text)] rounded text-xs hover:bg-[rgba(160,174,192,0.2)]"
                        >
                          {fragment.replace(/_/g, ' ')}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Preview and Generation */}
        <div className="space-y-6">
          {/* Generated Names Preview */}
          <div className=" rounded-xl shadow-sm border p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">🏷️ Generated Names Preview</h2>
              <button
                onClick={generateRandomNamesFromAPI}
                disabled={generatingNames}
                className="px-3 py-1 rounded text-sm font-bold uppercase tracking-wide transition-all disabled:opacity-50"
                style={{
                  background: 'rgba(168, 85, 247, 0.2)',
                  border: '1px solid #A855F7',
                  color: '#A855F7'
                }}
                onMouseEnter={(e) => {
                  if (!generatingNames) {
                    e.currentTarget.style.background = 'rgba(168, 85, 247, 0.3)'
                    e.currentTarget.style.boxShadow = '0 0 15px rgba(168, 85, 247, 0.5)'
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(168, 85, 247, 0.2)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                {generatingNames ? '🔄 Generating...' : '🎲 Generate Random Names'}
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <h4 className="font-medium text-sm text-[var(--aimaru-text)] mb-2">Variables</h4>
                <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                  {Object.entries((apiGeneratedNames || generatedNames).variables).slice(0, 4).map(([original, obfuscated]) => (
                    <div key={original} className="bg-[var(--aimaru-dark-surface)] p-2 rounded">
                      <div className="text-[var(--aimaru-text-dim)]">{original} →</div>
                      <div className="text-blue-600">{obfuscated}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="font-medium text-sm text-[var(--aimaru-text)] mb-2">Functions</h4>
                <div className="grid grid-cols-1 gap-2 text-xs font-mono max-h-32 overflow-y-auto">
                  {Object.entries((apiGeneratedNames || generatedNames).functions).slice(0, 4).map(([original, obfuscated]) => (
                    <div key={original} className="bg-[var(--aimaru-dark-surface)] p-2 rounded">
                      <div className="text-[var(--aimaru-text-dim)]">{original} →</div>
                      <div className="text-green-600">{obfuscated}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="font-medium text-sm text-[var(--aimaru-text)] mb-2">Constants</h4>
                <div className="grid grid-cols-1 gap-2 text-xs font-mono">
                  {Object.entries((apiGeneratedNames || generatedNames).constants).map(([original, obfuscated]) => (
                    <div key={original} className="bg-[var(--aimaru-dark-surface)] p-2 rounded">
                      <div className="text-[var(--aimaru-text-dim)]">{original} →</div>
                      <div className="text-purple-600">{obfuscated}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Build Results */}
          {buildResult && (
            <div className=" rounded-xl shadow-sm border p-6">
              <h2 className="text-lg font-semibold mb-4">📊 Build Results</h2>

              <div className="grid grid-cols-3 gap-4 mb-4">
                <StatusCard
                  title="Script Size"
                  value={`${buildResult.stats.size_kb} KB`}
                  color="blue"
                />
                <StatusCard
                  title="Lines of Code"
                  value={buildResult.stats.total_lines}
                  color="green"
                />
                <StatusCard
                  title="Functions"
                  value={buildResult.stats.functions}
                  color="purple"
                />
              </div>

              <div className="text-xs text-[var(--aimaru-text-dim)] bg-[var(--aimaru-dark-surface)] p-3 rounded-lg">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="font-medium">Build Info:</div>
                    <div>Build ID: {buildResult.build_id}</div>
                    <div>Timestamp: {new Date(buildResult.build_timestamp).toLocaleString()}</div>
                  </div>
                  <div>
                    <div className="font-medium">Security:</div>
                    <div>Obfuscation: {config.obfuscation_level.toUpperCase()}</div>
                    <div>Auth Method: {authMethod.toUpperCase()}</div>
                  </div>
                </div>
              </div>

              {generatedScript && (
                <div className="mt-4 space-y-2">
                  <button
                    onClick={getCompilationInstructions}
                    className="w-full px-3 py-2 bg-orange-500 text-white rounded-md hover:bg-orange-600 transition-colors"
                  >
                    📦 Get Compilation Instructions
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Deployment Instructions */}
          <div className=" rounded-xl shadow-sm border p-6">
            <h2 className="text-lg font-semibold mb-4">📖 Deployment Instructions</h2>

            <div className="space-y-3 text-sm">
              <div className="bg-blue-50 border-[var(--aimaru-dark-border)] border-[var(--aimaru-dark-border)] blue-200 rounded-lg p-3">
                <div className="font-medium text-blue-800 mb-1">API Key Authentication</div>
                <code className="text-xs text-blue-700 break-all">
                  .\mcp-client.ps1 -ServerBaseUrl "{serverUrl}" -ApiKey "ak_your_key_here"
                </code>
              </div>

              <div className="bg-green-50 border-[var(--aimaru-dark-border)] border-[var(--aimaru-dark-border)] green-200 rounded-lg p-3">
                <div className="font-medium text-green-800 mb-1">Username/Password Authentication</div>
                <code className="text-xs text-green-700 break-all">
                  .\mcp-client.ps1 -ServerBaseUrl "{serverUrl}" -Username "admin" -Password "password"
                </code>
              </div>

              <div className="bg-purple-50 border-[var(--aimaru-dark-border)] border-[var(--aimaru-dark-border)] purple-200 rounded-lg p-3">
                <div className="font-medium text-purple-800 mb-1">Silent Background Execution</div>
                <code className="text-xs text-purple-700 break-all">
                  powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File .\mcp-client.ps1 -ServerBaseUrl "{serverUrl}" -ApiKey "ak_key"
                </code>
              </div>

              {downloadFormat === 'base64' && (
                <div className="bg-orange-50 border-[var(--aimaru-dark-border)] border-[var(--aimaru-dark-border)] orange-200 rounded-lg p-3">
                  <div className="font-medium text-orange-800 mb-1">Base64 Execution</div>
                  <code className="text-xs text-orange-700 break-all">
                    $script = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((Get-Content script.txt))); Invoke-Expression $script
                  </code>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Script Preview */}
      {generatedScript && (
        <div className=" rounded-xl shadow-sm border p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">📄 Generated Script Preview</h2>
            <div className="flex gap-2">
              <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                {config.obfuscation_level.toUpperCase()} Obfuscation
              </span>
              <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-xs font-medium">
                {buildResult?.stats.size_kb} KB
              </span>
              <span className="px-2 py-1 bg-purple-100 text-purple-800 rounded text-xs font-medium">
                {downloadFormat.toUpperCase()}
              </span>
            </div>
          </div>

          <div className="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto max-h-96 font-mono text-xs">
            <pre className="whitespace-pre-wrap">{generatedScript.substring(0, 2000)}</pre>
            {generatedScript.length > 2000 && (
              <div className="text-[var(--aimaru-text-dim)] mt-2">
                ... ({(generatedScript.length - 2000)} more characters) ...
              </div>
            )}
          </div>

          <div className="mt-4 flex gap-2">
            <button
              onClick={() => {
                const fullPreview = window.open('', '_blank')
                if (fullPreview) {
                  fullPreview.document.write(`
                    <html>
                      <head><title>MCP Client - Full Preview</title></head>
                      <body style="margin:0;padding:20px;background:#1a1a1a;color:#00ff00;font-family:monospace;font-size:12px;">
                        <pre style="white-space:pre-wrap;word-wrap:break-word;">${generatedScript.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
                      </body>
                    </html>
                  `)
                  fullPreview.document.close()
                }
              }}
              className="px-3 py-1 bg-blue-500 text-white rounded text-sm hover:bg-blue-600"
            >
              👁️ Full Preview
            </button>
            <button
              onClick={() => {
                const lines = generatedScript.split('\n')
                const stats = {
                  totalLines: lines.length,
                  codeLines: lines.filter(l => l.trim() && !l.trim().startsWith('#')).length,
                  commentLines: lines.filter(l => l.trim().startsWith('#')).length,
                  functions: (generatedScript.match(/function\s+/g) || []).length,
                  variables: (generatedScript.match(/\$\w+/g) || []).length
                }
                alert(`Script Statistics:
Total Lines: ${stats.totalLines}
Code Lines: ${stats.codeLines}
Comment Lines: ${stats.commentLines}
Functions: ${stats.functions}
Variables: ${stats.variables}
Size: ${(generatedScript.length / 1024).toFixed(2)} KB`)
              }}
              className="px-3 py-1 bg-[var(--aimaru-dark-surface)]0 text-white rounded text-sm hover:bg-gray-600"
            >
              📊 Statistics
            </button>
          </div>
        </div>
      )}

      {/* Compilation Instructions Modal */}
      {compilationInstructions && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className=" rounded-xl shadow-xl max-w-4xl w-full max-h-[80vh] overflow-hidden">
            <div className="bg-[var(--aimaru-dark-surface)] px-6 py-4 border-b flex items-center justify-between">
              <h3 className="text-lg font-semibold">📦 Compilation Instructions</h3>
              <button
                onClick={() => setCompilationInstructions(null)}
                className="text-gray-400 hover:text-[var(--aimaru-text-dim)] text-2xl"
              >
                ×
              </button>
            </div>

            <div className="p-6 overflow-y-auto max-h-96">
              {Object.entries(compilationInstructions.compilation_methods || {}).map(([method, details]: [string, any]) => (
                <div key={method} className="mb-6 p-4 border rounded-lg">
                  <h4 className="font-semibold text-lg mb-2">{details.description}</h4>

                  {details.prerequisites && (
                    <div className="mb-3">
                      <span className="font-medium">Prerequisites: </span>
                      <code className="bg-[rgba(160,174,192,0.1)] px-2 py-1 rounded text-sm">{details.prerequisites}</code>
                    </div>
                  )}

                  {details.command && (
                    <div className="mb-3">
                      <span className="font-medium">Command: </span>
                      <div className="bg-gray-900 text-green-400 p-2 rounded font-mono text-sm mt-1">
                        {details.command}
                      </div>
                    </div>
                  )}

                  {details.steps && (
                    <div className="mb-3">
                      <span className="font-medium">Steps:</span>
                      <ol className="list-decimal list-inside mt-1 space-y-1">
                        {details.steps.map((step: string, i: number) => (
                          <li key={i} className="text-sm">{step}</li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {details.template_code && (
                    <div className="mb-3">
                      <span className="font-medium">Template Code:</span>
                      <div className="bg-gray-900 text-green-400 p-2 rounded font-mono text-xs mt-1 overflow-x-auto">
                        <pre>{details.template_code}</pre>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {compilationInstructions.recommendations && (
                <div className="mt-4 p-4 bg-blue-50 border-[var(--aimaru-dark-border)] border-[var(--aimaru-dark-border)] blue-200 rounded-lg">
                  <h4 className="font-semibold text-blue-800 mb-2">💡 Recommendations:</h4>
                  <ul className="list-disc list-inside text-sm text-blue-700 space-y-1">
                    {compilationInstructions.recommendations.map((rec: string, i: number) => (
                      <li key={i}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}

              {compilationInstructions.security_notes && (
                <div className="mt-4 p-4 bg-amber-50 border-[var(--aimaru-dark-border)] border-[var(--aimaru-dark-border)] amber-200 rounded-lg">
                  <h4 className="font-semibold text-amber-800 mb-2">⚠️ Security Notes:</h4>
                  <ul className="list-disc list-inside text-sm text-amber-700 space-y-1">
                    {compilationInstructions.security_notes.map((note: string, i: number) => (
                      <li key={i}>{note}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="bg-[var(--aimaru-dark-surface)] px-6 py-4 border-t flex justify-end">
              <button
                onClick={() => setCompilationInstructions(null)}
                className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Security Notice */}
      <div className="bg-amber-50 border-[var(--aimaru-dark-border)] border-[var(--aimaru-dark-border)] amber-200 rounded-xl p-6">
        <div className="flex items-start">
          <div className="text-amber-500 mr-3 mt-0.5">⚠️</div>
          <div>
            <h3 className="font-semibold text-amber-800 mb-2">Security & Usage Notice</h3>
            <div className="text-amber-700 text-sm space-y-1">
              <p>• Generated clients maintain full compatibility with your MCP server infrastructure</p>
              <p>• Obfuscation helps avoid detection but does not change core cryptographic functionality</p>
              <p>• Each generated client has unique variable names and constants based on your configuration</p>
              <p>• All cryptographic operations (HKDF, AES-256-CBC, HMAC-SHA256) remain unchanged and secure</p>
              <p>• Test generated clients in a safe environment before production deployment</p>
              <p>• Higher obfuscation levels may increase script size and execution time</p>
              <p>• Generated clients are designed to be functionally identical to the original PSMCP.ps1</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
