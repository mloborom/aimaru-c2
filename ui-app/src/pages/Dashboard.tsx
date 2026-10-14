// ui-app/src/pages/Dashboard.tsx - AIMARU CYBERPUNK THEME
import React, { useEffect, useState, useMemo } from 'react'
import { useAuth } from '../auth/AuthContext'
import MCPClientBuilder from '../components/MCPClientBuilder'
import {
  ATTACK_TACTICS, TACTIC_COLORS, TECHNIQUE_TO_TACTIC, TECHNIQUE_NAMES,
  parseMessagesForTTPs, getTacticStatus,
  getFreeSystemPrompt, getGuideSystemPrompt, KILL_CHAIN_BOOTSTRAP,
  ATTACKTactic
} from '../lib/killchain'

interface ClientSummary {
  id: string
  connected: boolean
  last_seen_at: string | null
  queued: number
  delivered: number
  completed: number
  total: number
  amsi_bypassed?: boolean
}

interface QueueItem {
  id: string
  client_id: string
  status: 'queued' | 'delivered' | 'completed'
  created_at: string
  command_plain: string
  has_result: boolean
}

interface ChatMessage {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tool_name?: string
  tool_args?: string
  created_at: string
}

interface ChatSession {
  id: string
  client_id: string
  owner_user_id: string
  llm_config_id?: string
  system_prompt?: string
  created_at: string
  message_count?: number
  last_message_at?: string
}

interface LLMConfig {
  id: string
  name: string
  provider: string
  model: string
  temperature: number
  is_active: boolean
}

interface InstructionResult {
  id: string
  client_id: string
  status: string
  created_at: string
  delivered_at?: string
  completed_at?: string
  command_plain?: string
  result_plain_b64?: string
  plaintext?: string
}

// CSS for message animations
const messageAnimationCSS = `
  @keyframes fadeInSlide {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .message-animate {
    animation: fadeInSlide 0.3s ease-out forwards;
  }

  .progress-spinner {
    display: inline-block;
    width: 12px;
    height: 12px;
    border: 2px solid rgba(0, 229, 204, 0.3);
    border-top-color: #00E5CC;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
`

export default function Dashboard() {
  const { token, api } = useAuth()
  const [clients, setClients] = useState<ClientSummary[]>([])
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [chatSessions, setChatSessions] = useState<ChatSession[]>([])
  const [llmConfigs, setLlmConfigs] = useState<LLMConfig[]>([])
  const [selectedLLMConfig, setSelectedLLMConfig] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  // Chat state
  const [selectedClient, setSelectedClient] = useState<string | null>(null)
  const [currentSession, setCurrentSession] = useState<string | null>(null)
  const [chatMode, setChatMode] = useState<'free' | 'guide'>('free')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [newMessage, setNewMessage] = useState('')
  const [sendingMessage, setSendingMessage] = useState(false)
  const [messageAnimationIndices, setMessageAnimationIndices] = useState<Set<string>>(new Set())
  const [showDirectCommands, setShowDirectCommands] = useState(false)
  const [directCommand, setDirectCommand] = useState('')

  // Result viewing state
  const [viewingResult, setViewingResult] = useState<InstructionResult | null>(null)
  const [resultLoading, setResultLoading] = useState(false)

  // Direct Commands Panel with Script Upload
  const [scriptFile, setScriptFile] = useState<File | null>(null)
  const [scriptContent, setScriptContent] = useState('')
  const [scriptMode, setScriptMode] = useState<'command' | 'upload' | 'editor'>('command')
  const [executingScript, setExecutingScript] = useState(false)
  const [scriptResult, setScriptResult] = useState<string | null>(null)

  // View state - Updated to include 'builder' and 'tools' tabs
  const [activeTab, setActiveTab] = useState<'overview' | 'chat' | 'queue' | 'builder' | 'tools'>('overview')

  // Predefined Tools state
  const [generatingTool, setGeneratingTool] = useState(false)
  const [generatedToolScript, setGeneratedToolScript] = useState<string | null>(null)
  const [toolScriptName, setToolScriptName] = useState<string>('')
  const [toolUsageInstructions, setToolUsageInstructions] = useState<string>('')
  const [hoveredTacticId, setHoveredTacticId] = useState<string | null>(null)

  async function loadData() {
    if (!token) return
    setLoading(true)

    try {
      // Load data sequentially to avoid database concurrency issues
      const clientsData = await fetch('/api/clients', {
        headers: { 'Authorization': `Bearer ${token}` },
        credentials: 'include'
      }).then(r => r.json())

      const queueData = await api.listQueue()

      setClients(clientsData.clients || [])
      setQueue(queueData || [])

      // Load LLM configs and chat sessions with error handling
      try {
        const llmConfigsData = await fetch('/api/llm/configs', {
          headers: { 'Authorization': `Bearer ${token}` },
          credentials: 'include'
        }).then(r => r.ok ? r.json() : { configs: [] })

        setLlmConfigs(llmConfigsData.configs || [])

        // Auto-select first active LLM config if none selected
        if (!selectedLLMConfig && llmConfigsData.configs?.length > 0) {
          const activeConfig = llmConfigsData.configs.find((c: LLMConfig) => c.is_active)
          if (activeConfig) {
            setSelectedLLMConfig(activeConfig.id)
          }
        }
      } catch (e) {
        console.warn('LLM configs not available:', e)
        setLlmConfigs([])
      }

      // Load chat sessions separately with error handling
      try {
        const sessionsData = await fetch('/api/chat/sessions', {
          headers: { 'Authorization': `Bearer ${token}` },
          credentials: 'include'
        }).then(r => r.ok ? r.json() : { sessions: [] })

        setChatSessions(sessionsData.sessions || [])
      } catch (e) {
        console.warn('Chat sessions not available - tables may not exist:', e)
        setChatSessions([])
      }

    } catch (e: any) {
      console.error('Failed to load dashboard data:', e)
      setErr(`Failed to load data: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  async function startChatSession(mode: 'free' | 'guide' = chatMode) {
    if (!selectedLLMConfig) {
      alert('Please configure an LLM model first in the LLM settings.')
      return
    }
    if (!selectedClient) return

    try {
      const systemPrompt = mode === 'guide'
        ? getGuideSystemPrompt(selectedClient)
        : getFreeSystemPrompt(selectedClient)

      const response = await fetch('/api/chat/sessions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({
          client_id: selectedClient,
          llm_config_id: selectedLLMConfig,
          system_prompt: systemPrompt
        })
      })

      if (!response.ok) {
        throw new Error(`Failed to create session: ${response.statusText}`)
      }

      const session = await response.json()
      setChatMode(mode)
      setCurrentSession(session.id)

      // Guide mode: send bootstrap to trigger Discovery immediately
      if (mode === 'guide') {
        await fetch('/api/chat/message', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          credentials: 'include',
          body: JSON.stringify({ session_id: session.id, message: KILL_CHAIN_BOOTSTRAP })
        })
      }

      await loadSessionMessages(session.id)

    } catch (e: any) {
      console.error('Failed to start chat session:', e)
      alert(`Failed to start chat session: ${e.message}`)
    }
  }

  async function loadSessionMessages(sessionId: string, forceScroll = false) {
    try {
      const response = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
        headers: { 'Authorization': `Bearer ${token}` },
        credentials: 'include'
      })

      if (response.ok) {
        const data = await response.json()

        // Capture scroll state BEFORE React re-renders (avoids stale read after setState)
        const container = document.querySelector('.messages-container')
        const wasNearBottom = !container || (
          container.scrollHeight - container.scrollTop - container.clientHeight < 150
        )

        setMessages(data.messages || [])

        // Only scroll to bottom if user was already at the bottom, or explicitly forced
        // (e.g. right after the user sends a message). If they scrolled up to read a long
        // response, we leave their position alone.
        if (forceScroll || wasNearBottom) {
          setTimeout(() => {
            const c = document.querySelector('.messages-container')
            if (c) c.scrollTop = c.scrollHeight
          }, 100)
        }
      }
    } catch (e) {
      console.error('Failed to load session messages:', e)
    }
  }

  async function sendChatMessage() {
    if (!newMessage.trim() || !selectedClient || !currentSession) return

    setSendingMessage(true)

    try {
      const response = await fetch('/api/chat/message', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({
          session_id: currentSession,
          message: newMessage.trim()
        })
      })

      if (!response.ok) {
        throw new Error(`Failed to send message: ${response.statusText}`)
      }

      setNewMessage('')

      // User just sent — always scroll to bottom to show their message + incoming response
      await loadSessionMessages(currentSession, true)

    } catch (e: any) {
      console.error('Failed to send message:', e)
      alert(`Failed to send message: ${e.message}`)
    } finally {
      setSendingMessage(false)
    }
  }

  async function jumpToTactic(tactic: ATTACKTactic) {
    if (!currentSession || chatMode !== 'guide') return
    const directive = `Jump to [${tactic.id}] ${tactic.name.toUpperCase()} now. Autonomously execute all relevant techniques for this tactic using execute_powershell — adapt commands based on what you already know about this target. Tag each technique as you go and output [${tactic.id}] COMPLETE when done.`
    setSendingMessage(true)
    try {
      const res = await fetch('/api/chat/message', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ session_id: currentSession, message: directive })
      })
      if (!res.ok) throw new Error(res.statusText)
      await loadSessionMessages(currentSession, true)
    } catch (e: any) {
      console.error('jumpToTactic failed:', e)
    } finally {
      setSendingMessage(false)
    }
  }

  async function executeScript() {
    if (!selectedClient) return

    let scriptToExecute = ''
    let scriptName = 'Direct Command'

    if (scriptMode === 'command') {
      scriptToExecute = directCommand
      scriptName = 'Direct Command'
    } else if (scriptMode === 'upload' && scriptFile) {
      scriptToExecute = await readFileAsText(scriptFile)
      scriptName = scriptFile.name
    } else if (scriptMode === 'editor') {
      scriptToExecute = scriptContent
      scriptName = 'Script Editor'
    }

    if (!scriptToExecute.trim()) {
      alert('Please provide a script or command to execute')
      return
    }

    setExecutingScript(true)
    setScriptResult(null)

    try {
      // Use enhanced script execution endpoint if it's a multi-line script
      const isMultiLineScript = scriptToExecute.includes('\n') || scriptMode !== 'command'

      const endpoint = isMultiLineScript ? '/api/execute-script' : '/api/issue-command'
      const requestBody = isMultiLineScript ? {
        client_id: selectedClient,
        script_content: scriptToExecute,
        script_name: scriptName,
        execution_mode: scriptMode
      } : {
        client_id: selectedClient,
        command: scriptToExecute
      }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify(requestBody)
      })

      if (!response.ok) {
        throw new Error(`Failed to execute script: ${response.statusText}`)
      }

      const result = await response.json()

      // Clear inputs
      setDirectCommand('')
      setScriptContent('')
      setScriptFile(null)

      // Show immediate feedback
      if (isMultiLineScript) {
        const resultMessage = `Script "${scriptName}" submitted for execution...
Lines: ${result.lines_count || 'N/A'}
Characters: ${result.characters_count || 'N/A'}
Mode: ${result.execution_mode || scriptMode}

Waiting for results...`
        setScriptResult(resultMessage)
      } else {
        setScriptResult(`Command submitted: ${scriptToExecute}\n\nWaiting for results...`)
      }

      // Get the instruction ID to monitor for results
      if (result.instruction_id) {
        // Poll for results
        pollForScriptResult(result.instruction_id)
      }

      // Add to chat if session exists
      if (currentSession) {
        try {
          const chatMessage = isMultiLineScript
            ? `[PowerShell Script: ${scriptName}]\nMode: ${scriptMode}\n${scriptToExecute.substring(0, 200)}${scriptToExecute.length > 200 ? '...' : ''}`
            : `[Direct Command] ${scriptToExecute}`

          await fetch('/api/chat/message', {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
              session_id: currentSession,
              message: chatMessage,
              role: 'system'
            })
          })

          await loadSessionMessages(currentSession)
        } catch (e) {
          console.error('Failed to log script to chat:', e)
        }
      }

      // Refresh queue
      setTimeout(loadData, 1000)

    } catch (e: any) {
      console.error('Failed to execute script:', e)
      alert(`Failed to execute script: ${e.message}`)
      setScriptResult(`Error: ${e.message}`)
    } finally {
      setExecutingScript(false)
    }
  }

  async function readFileAsText(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = (e) => resolve(e.target?.result as string)
      reader.onerror = (e) => reject(e)
      reader.readAsText(file)
    })
  }

  async function pollForScriptResult(instructionId: string) {
    let attempts = 0
    const maxAttempts = 30 // 30 seconds max

    const poll = async () => {
      try {
        attempts++
        const instruction = await api.result(instructionId)

        if (instruction.status === 'completed') {
          let resultContent = 'No result available'

          if (instruction.result_plain_b64) {
            try {
              resultContent = atob(instruction.result_plain_b64)
            } catch (e) {
              resultContent = 'Error decoding result'
            }
          } else if (instruction.plaintext) {
            resultContent = instruction.plaintext
          }

          setScriptResult(resultContent)
          return
        }

        if (instruction.status === 'error') {
          setScriptResult(`Script execution failed: ${instruction.error || 'Unknown error'}`)
          return
        }

        // Continue polling if not completed and under max attempts
        if (attempts < maxAttempts && (instruction.status === 'queued' || instruction.status === 'delivered')) {
          setTimeout(poll, 1000) // Poll every second
        } else if (attempts >= maxAttempts) {
          setScriptResult('Timeout waiting for script result. Check the queue for status.')
        }

      } catch (e: any) {
        console.error('Error polling for result:', e)
        if (attempts >= maxAttempts) {
          setScriptResult(`Error getting result: ${e.message}`)
        } else {
          setTimeout(poll, 1000)
        }
      }
    }

    // Start polling after a short delay
    setTimeout(poll, 2000)
  }

  function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (file) {
      if (file.name.toLowerCase().endsWith('.ps1') || file.name.toLowerCase().endsWith('.txt')) {
        setScriptFile(file)
        setScriptResult(null)
      } else {
        alert('Please select a .ps1 or .txt file')
        event.target.value = ''
      }
    }
  }

  async function viewResult(instructionId: string) {
    setResultLoading(true)
    setViewingResult(null)

    try {
      const result = await api.result(instructionId)
      setViewingResult(result)
    } catch (e: any) {
      console.error('Failed to load result:', e)
      alert(`Failed to load result: ${e.message}`)
    } finally {
      setResultLoading(false)
    }
  }

  async function viewResultInChat(instructionId: string) {
    try {
      const result = await api.result(instructionId)
      setViewingResult(result)

      // Scroll to bottom to show the result
      setTimeout(() => {
        const messagesContainer = document.querySelector('.overflow-y-auto')
        if (messagesContainer) {
          messagesContainer.scrollTop = messagesContainer.scrollHeight
        }
      }, 100)
    } catch (e: any) {
      console.error('Failed to load result in chat:', e)
      alert(`Failed to load result: ${e.message}`)
    }
  }

  async function generateToolScript(toolName: string, config: any = {}) {
    if (!token) return

    setGeneratingTool(true)
    try {
      const response = await fetch('/api/tools/generate', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({
          tool_name: toolName,
          config: config
        })
      })

      if (!response.ok) {
        throw new Error(`Failed to generate script: ${response.statusText}`)
      }

      const data = await response.json()
      setGeneratedToolScript(data.script)
      setToolScriptName(data.tool_name)
      setToolUsageInstructions(data.usage_instructions)

      // Show success message
      alert(`✅ ${data.tool_name} script generated successfully!\n\nSize: ${(data.script_size_bytes / 1024).toFixed(2)} KB`)
    } catch (e: any) {
      console.error('Failed to generate tool script:', e)
      alert(`❌ Failed to generate script: ${e.message}`)
    } finally {
      setGeneratingTool(false)
    }
  }

  function downloadToolScript() {
    if (!generatedToolScript || !toolScriptName) return

    const blob = new Blob([generatedToolScript], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${toolScriptName}_${Date.now()}.ps1`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  function copyToolScriptToClipboard() {
    if (!generatedToolScript) return

    navigator.clipboard.writeText(generatedToolScript).then(() => {
      alert('✅ Script copied to clipboard!')
    }).catch(err => {
      console.error('Failed to copy:', err)
      alert('❌ Failed to copy to clipboard')
    })
  }

  function closeResultModal() {
    setViewingResult(null)
  }

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 5000)
    return () => clearInterval(interval)
  }, [token])

  // Auto-refresh messages when in chat mode with active session
  useEffect(() => {
    if (currentSession && activeTab === 'chat') {
      const interval = setInterval(() => {
        loadSessionMessages(currentSession)
      }, 3000) // Refresh messages every 3 seconds
      return () => clearInterval(interval)
    }
  }, [currentSession, activeTab])

  // SSE stream for real-time chat messages
  useEffect(() => {
    if (!currentSession || activeTab !== 'chat') return

    const eventSource = new EventSource(`/api/chat/stream/${currentSession}?token=${encodeURIComponent(token)}`, {
      withCredentials: true
    })

    eventSource.addEventListener('message', (event) => {
      try {
        const message = JSON.parse(event.data)
        setMessages((prev) => {
          // Check if message already exists
          if (prev.some(m => m.id === message.id)) {
            return prev
          }
          return [...prev, message]
        })

        // Auto-scroll to bottom
        setTimeout(() => {
          const container = document.querySelector('.messages-container')
          if (container) container.scrollTop = container.scrollHeight
        }, 0)
      } catch (e) {
        console.error('Failed to parse SSE message:', e)
      }
    })

    eventSource.onerror = () => {
      console.warn('[chat] SSE connection lost, falling back to polling')
      eventSource.close()
    }

    return () => eventSource.close()
  }, [currentSession, activeTab, token])

  const stats = useMemo(() => {
    const connected = clients.filter(c => c.connected)
    const disconnected = clients.filter(c => !c.connected)
    const totalInstructions = queue.length
    const queueStats = queue.reduce((acc, item) => {
      acc[item.status] = (acc[item.status] || 0) + 1
      return acc
    }, {} as Record<string, number>)

    return {
      total: clients.length,
      connected: connected.length,
      disconnected: disconnected.length,
      totalInstructions,
      queued: queueStats.queued || 0,
      completed: queueStats.completed || 0,
      delivered: queueStats.delivered || 0
    }
  }, [clients, queue])

  // ========================================
  // AIMARU CYBERPUNK STYLED COMPONENTS
  // ========================================

  const StatusCard = ({ title, value, subtitle, color = 'blue' }: {
    title: string, value: number, subtitle?: string, color?: 'blue' | 'green' | 'red' | 'yellow'
  }) => {
    const colors = {
      blue: { bg: 'rgba(0, 229, 204, 0.1)', border: 'var(--aimaru-cyan)', text: 'var(--aimaru-cyan)' },
      green: { bg: 'rgba(16, 185, 129, 0.1)', border: '#10B981', text: '#10B981' },
      red: { bg: 'rgba(239, 68, 68, 0.1)', border: '#EF4444', text: '#EF4444' },
      yellow: { bg: 'rgba(251, 191, 36, 0.1)', border: '#FBB036', text: '#FBB036' }
    }

    const colorScheme = colors[color]

    return (
      <div className="rounded-lg border p-4 glow-cyan transition-all hover:scale-105 cursor-pointer"
           style={{
             background: colorScheme.bg,
             borderColor: colorScheme.border,
             boxShadow: `0 0 15px ${colorScheme.border}40`
           }}>
        <div className="text-3xl font-bold mb-1 glow-text-cyan" style={{ color: colorScheme.text }}>
          {value}
        </div>
        <div className="text-sm font-medium uppercase tracking-wide" style={{ color: 'var(--aimaru-text)' }}>
          {title}
        </div>
        {subtitle && <div className="text-xs mt-1" style={{ color: 'var(--aimaru-text-dim)' }}>{subtitle}</div>}
      </div>
    )
  }

  const ClientCard = ({ client }: { client: ClientSummary }) => (
    <div className="rounded-lg border p-4 transition-all hover:scale-105 scan-line"
         style={{
           background: 'var(--aimaru-dark-card)',
           borderColor: client.connected ? 'var(--aimaru-cyan)' : 'var(--aimaru-dark-border)',
           boxShadow: client.connected ? '0 0 20px rgba(0, 229, 204, 0.2)' : '0 0 10px rgba(26, 31, 46, 0.5)'
         }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl" title={client.amsi_bypassed ? "AMSI Bypassed - Protection Disabled" : "AMSI Active - Protected"}>
            {client.amsi_bypassed ? '🛡️💥' : '🛡️'}
          </span>
          <div className="font-bold text-lg" style={{ color: 'var(--aimaru-text)' }}>
            {client.id}
          </div>
        </div>
        <div className={`px-3 py-1 rounded-full text-xs font-bold flex items-center gap-2 ${
          client.connected ? 'badge-online pulse-glow' : 'badge-offline'
        }`}>
          <span className={`w-2 h-2 rounded-full ${client.connected ? 'status-online' : 'status-offline'}`}></span>
          {client.connected ? 'ONLINE' : 'OFFLINE'}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2 text-xs mb-3" style={{ color: 'var(--aimaru-text-dim)' }}>
        <div className="text-center">
          <div className="text-yellow-500 font-bold">{client.queued}</div>
          <div>Queued</div>
        </div>
        <div className="text-center">
          <div className="text-blue-500 font-bold">{client.delivered}</div>
          <div>Sent</div>
        </div>
        <div className="text-center">
          <div className="text-green-500 font-bold">{client.completed}</div>
          <div>Done</div>
        </div>
        <div className="text-center">
          <div style={{ color: 'var(--aimaru-cyan)' }} className="font-bold">{client.total}</div>
          <div>Total</div>
        </div>
      </div>

      {client.last_seen_at && (
        <div className="text-xs mb-3 font-mono" style={{ color: 'var(--aimaru-text-dim)' }}>
          Last: {new Date(client.last_seen_at).toLocaleString()}
        </div>
      )}

      <div className="flex gap-2">
        {client.connected && (
          <button
            onClick={() => {
              setSelectedClient(client.id)
              setCurrentSession(null)
              setMessages([])
              setActiveTab('chat')
            }}
            className="flex-1 px-3 py-2 rounded-md text-sm font-bold transition-all"
            style={{
              background: 'rgba(0, 229, 204, 0.2)',
              border: '1px solid var(--aimaru-cyan)',
              color: 'var(--aimaru-cyan)'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(0, 229, 204, 0.3)'
              e.currentTarget.style.boxShadow = '0 0 15px rgba(0, 229, 204, 0.5)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(0, 229, 204, 0.2)'
              e.currentTarget.style.boxShadow = 'none'
            }}
          >
            🤖 AI CHAT
          </button>
        )}
        <button
          onClick={() => {
            setSelectedClient(client.id)
            setActiveTab('queue')
          }}
          className="px-3 py-2 rounded-md text-sm font-bold transition-all"
          style={{
            background: 'rgba(160, 174, 192, 0.2)',
            border: '1px solid var(--aimaru-gray)',
            color: 'var(--aimaru-text)'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(160, 174, 192, 0.3)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(160, 174, 192, 0.2)'
          }}
        >
          📋 QUEUE
        </button>
      </div>
    </div>
  )

  // Result Modal Component
  const ResultModal = () => {
    if (!viewingResult) return null

    let resultContent = 'No result content available'
    let isDecryptionError = false

    if (viewingResult.result_plain_b64) {
      try {
        resultContent = atob(viewingResult.result_plain_b64)
      } catch (e) {
        resultContent = 'Error decoding result content'
        isDecryptionError = true
      }
    } else if (viewingResult.plaintext) {
      resultContent = viewingResult.plaintext

      // Check if this is a decryption error message
      if (resultContent.includes('Key not available') ||
          resultContent.includes('cannot decrypt') ||
          resultContent.includes('Decrypt failed')) {
        isDecryptionError = true
      }
    }

    // Check if client is currently connected
    const clientConnected = clients.find(c => c.id === viewingResult.client_id)?.connected || false

    return (
      <div className="fixed inset-0 flex items-center justify-center z-50 p-4"
           style={{ background: 'rgba(10, 14, 26, 0.95)' }}>
        <div className="rounded-xl max-w-4xl w-full max-h-[80vh] overflow-hidden glow-cyan-strong"
             style={{
               background: 'var(--aimaru-dark-surface)',
               border: '2px solid var(--aimaru-cyan)'
             }}>
          <div className="px-6 py-4 border-b flex items-center justify-between scan-line"
               style={{ borderColor: 'var(--aimaru-dark-border)' }}>
            <div>
              <h3 className="text-lg font-bold glow-text-cyan" style={{ color: 'var(--aimaru-cyan)' }}>
                INSTRUCTION RESULT
              </h3>
              <p className="text-sm" style={{ color: 'var(--aimaru-text-dim)' }}>
                {viewingResult.client_id} • {new Date(viewingResult.created_at).toLocaleString()}
              </p>
            </div>
            <button
              onClick={closeResultModal}
              className="text-4xl font-bold transition-all"
              style={{ color: 'var(--aimaru-text-dim)' }}
              onMouseEnter={(e) => e.currentTarget.style.color = 'var(--aimaru-cyan)'}
              onMouseLeave={(e) => e.currentTarget.style.color = 'var(--aimaru-text-dim)'}
            >
              ×
            </button>
          </div>

          <div className="p-6 overflow-y-auto max-h-[60vh]">
            <div className="mb-4">
              <h4 className="font-bold mb-2 uppercase tracking-wide" style={{ color: 'var(--aimaru-cyan)' }}>
                Command Executed:
              </h4>
              <div className="p-3 rounded-md font-mono text-sm"
                   style={{
                     background: 'rgba(0, 229, 204, 0.05)',
                     border: '1px solid var(--aimaru-dark-border)',
                     color: 'var(--aimaru-text)'
                   }}>
                {viewingResult.command_plain || 'Command not available'}
              </div>
            </div>

            <div className="mb-4">
              <h4 className="font-bold mb-2 uppercase tracking-wide" style={{ color: 'var(--aimaru-cyan)' }}>
                Execution Timeline:
              </h4>
              <div className="text-sm space-y-1 font-mono" style={{ color: 'var(--aimaru-text-dim)' }}>
                <div>Created: {new Date(viewingResult.created_at).toLocaleString()}</div>
                {viewingResult.delivered_at && (
                  <div>Delivered: {new Date(viewingResult.delivered_at).toLocaleString()}</div>
                )}
                {viewingResult.completed_at && (
                  <div>Completed: {new Date(viewingResult.completed_at).toLocaleString()}</div>
                )}
              </div>
            </div>

            <div>
              <h4 className="font-bold mb-2 uppercase tracking-wide" style={{ color: 'var(--aimaru-cyan)' }}>
                Result Output:
              </h4>

              {/* Decryption Error Warning */}
              {isDecryptionError && (
                <div className="mb-4 p-4 rounded-lg"
                     style={{
                       background: 'rgba(251, 191, 36, 0.1)',
                       border: '1px solid #FBB036',
                       boxShadow: '0 0 15px rgba(251, 191, 36, 0.2)'
                     }}>
                  <div className="flex items-start gap-3">
                    <div className="text-2xl">⚠️</div>
                    <div>
                      <h5 className="font-bold text-sm mb-1 uppercase tracking-wide"
                          style={{ color: '#FBB036' }}>
                        {clientConnected ? 'DECRYPTION ERROR' : 'CLIENT OFFLINE'}
                      </h5>
                      <p className="text-xs font-mono" style={{ color: 'var(--aimaru-text)' }}>
                        {clientConnected
                          ? 'The result could not be decrypted. This may indicate a key mismatch or corrupted data.'
                          : 'The client is currently offline. Results cannot be decrypted because the encryption key is only available when the client is connected. Please wait for the client to reconnect to view the result.'}
                      </p>
                      {!clientConnected && (
                        <div className="mt-2 text-xs font-bold" style={{ color: '#FBB036' }}>
                          💡 Tip: Results are encrypted end-to-end. The decryption key is held in memory only while the client is connected.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="p-4 rounded-md overflow-auto max-h-96 font-mono text-sm glow-cyan"
                   style={{
                     background: '#000',
                     color: isDecryptionError ? '#FBB036' : 'var(--aimaru-cyan)',
                     border: `1px solid ${isDecryptionError ? '#FBB036' : 'var(--aimaru-cyan)'}`,
                     boxShadow: isDecryptionError
                       ? '0 0 20px rgba(251, 191, 36, 0.3), inset 0 0 20px rgba(251, 191, 36, 0.05)'
                       : '0 0 20px rgba(0, 229, 204, 0.3), inset 0 0 20px rgba(0, 229, 204, 0.05)'
                   }}>
                <div style={{ color: '#10B981', marginBottom: '8px' }}>
                  PS {viewingResult.client_id}&gt; # Output
                </div>
                <pre className="whitespace-pre-wrap">{resultContent}</pre>
              </div>
            </div>
          </div>

          <div className="px-6 py-4 border-t flex justify-end"
               style={{ borderColor: 'var(--aimaru-dark-border)' }}>
            <button
              onClick={closeResultModal}
              className="px-6 py-2 rounded-md font-bold transition-all"
              style={{
                background: 'rgba(0, 229, 204, 0.2)',
                border: '1px solid var(--aimaru-cyan)',
                color: 'var(--aimaru-cyan)'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(0, 229, 204, 0.3)'
                e.currentTarget.style.boxShadow = '0 0 15px rgba(0, 229, 204, 0.5)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(0, 229, 204, 0.2)'
                e.currentTarget.style.boxShadow = 'none'
              }}
            >
              CLOSE
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!token) {
    return (
      <div className="rounded-2xl p-6 glow-cyan"
           style={{
             background: 'rgba(239, 68, 68, 0.1)',
             border: '1px solid #EF4444',
             color: '#EF4444'
           }}>
        <div className="font-bold text-lg mb-2">AUTHENTICATION REQUIRED</div>
        Please <a href="/login" className="underline font-bold">log in</a> to access the dashboard.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <style>{messageAnimationCSS}</style>
      {err && (
        <div className="rounded-xl p-4 glow-cyan"
             style={{
               background: 'rgba(239, 68, 68, 0.1)',
               border: '1px solid #EF4444'
             }}>
          <div className="flex items-start">
            <span className="mr-2 mt-0.5 text-2xl">⚠️</span>
            <div className="flex-1">
              <div className="font-bold" style={{ color: '#EF4444' }}>ERROR</div>
              <div className="text-sm mt-1" style={{ color: 'var(--aimaru-text)' }}>{err}</div>
            </div>
            <button
              onClick={() => setErr('')}
              className="ml-2 text-2xl font-bold transition-all"
              style={{ color: 'var(--aimaru-text-dim)' }}
              onMouseEnter={(e) => e.currentTarget.style.color = '#EF4444'}
              onMouseLeave={(e) => e.currentTarget.style.color = 'var(--aimaru-text-dim)'}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold glow-text-cyan" style={{ color: 'var(--aimaru-cyan)' }}>
            COMMAND CENTER
          </h1>
          <p className="text-sm mt-1 font-mono" style={{ color: 'var(--aimaru-text-dim)' }}>
            Real-time client management and control
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="px-6 py-3 rounded-lg font-bold transition-all disabled:opacity-50"
          style={{
            background: loading ? 'rgba(0, 229, 204, 0.1)' : 'rgba(0, 229, 204, 0.2)',
            border: '1px solid var(--aimaru-cyan)',
            color: 'var(--aimaru-cyan)'
          }}
          onMouseEnter={(e) => {
            if (!loading) {
              e.currentTarget.style.background = 'rgba(0, 229, 204, 0.3)'
              e.currentTarget.style.boxShadow = '0 0 20px rgba(0, 229, 204, 0.5)'
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(0, 229, 204, 0.2)'
            e.currentTarget.style.boxShadow = 'none'
          }}
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <div className="cyber-loading"></div>
              LOADING...
            </span>
          ) : (
            '⟳ REFRESH'
          )}
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <StatusCard title="Total Clients" value={stats.total} color="blue" />
        <StatusCard title="Connected" value={stats.connected} color="green" />
        <StatusCard title="Disconnected" value={stats.disconnected} color="red" />
        <StatusCard title="Instructions" value={stats.totalInstructions} color="blue" />
        <StatusCard title="Queued" value={stats.queued} color="yellow" />
        <StatusCard title="Delivered" value={stats.delivered} color="blue" />
        <StatusCard title="Completed" value={stats.completed} color="green" />
      </div>

      <div className="border-b" style={{ borderColor: 'var(--aimaru-dark-border)' }}>
        <nav className="-mb-px flex space-x-8">
          {[
            { id: 'overview', label: '🏠 OVERVIEW', count: stats.connected },
            { id: 'chat', label: '🤖 AI CHAT', count: selectedClient ? 1 : 0 },
            { id: 'queue', label: '📋 QUEUE', count: stats.totalInstructions },
            { id: 'builder', label: '🔧 BUILDER', count: 0 },
            { id: 'tools', label: '⚡ TOOLS', count: 0 }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`py-3 px-2 border-b-2 font-bold text-sm transition-all uppercase tracking-wide ${
                activeTab === tab.id
                  ? 'glow-text-cyan'
                  : ''
              }`}
              style={{
                borderColor: activeTab === tab.id ? 'var(--aimaru-cyan)' : 'transparent',
                color: activeTab === tab.id ? 'var(--aimaru-cyan)' : 'var(--aimaru-text-dim)'
              }}
              onMouseEnter={(e) => {
                if (activeTab !== tab.id) {
                  e.currentTarget.style.color = 'var(--aimaru-text)'
                }
              }}
              onMouseLeave={(e) => {
                if (activeTab !== tab.id) {
                  e.currentTarget.style.color = 'var(--aimaru-text-dim)'
                }
              }}
            >
              {tab.label} {tab.count > 0 && (
                <span className="ml-2 px-2 py-0.5 rounded-full text-xs font-bold"
                      style={{
                        background: 'rgba(0, 229, 204, 0.2)',
                        color: 'var(--aimaru-cyan)'
                      }}>
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="rounded-xl p-5 scan-line"
               style={{
                 background: 'rgba(0, 229, 204, 0.15)',
                 border: '2px solid rgba(0,229,204,0.5)',
                 boxShadow: '0 0 30px rgba(0,229,204,0.25)'
               }}>
            <h2 className="text-xl font-bold mb-4 uppercase tracking-wide"
                style={{ color: 'var(--aimaru-cyan)', textShadow: '0 2px 8px rgba(0,0,0,0.5)' }}>
              📡 Connected Devices ({stats.connected})
            </h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {clients.filter(c => c.connected).map(client => (
                <ClientCard key={client.id} client={client} />
              ))}
              {stats.connected === 0 && (
                <div className="col-span-full text-center py-12"
                     style={{ color: 'var(--aimaru-text-dim)' }}>
                  <div className="text-4xl mb-3">📡</div>
                  <div className="font-mono">No devices currently connected</div>
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl p-5"
               style={{
                 background: 'rgba(239, 68, 68, 0.12)',
                 border: '2px solid rgba(239,68,68,0.5)',
                 boxShadow: '0 0 30px rgba(239,68,68,0.2)'
               }}>
            <h2 className="text-xl font-bold mb-4 uppercase tracking-wide"
                style={{ color: '#FF6B6B', textShadow: '0 2px 8px rgba(0,0,0,0.5)' }}>
              ⚠️ Offline Devices ({stats.disconnected})
            </h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
              {clients.filter(c => !c.connected).map(client => (
                <ClientCard key={client.id} client={client} />
              ))}
              {stats.disconnected === 0 && (
                <div className="col-span-full text-center py-12"
                     style={{ color: 'var(--aimaru-text-dim)' }}>
                  <div className="text-4xl mb-3">✅</div>
                  <div className="font-mono">All devices are currently connected</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* CHAT AND QUEUE TABS - Continue with existing implementation but with Aimaru styling */}
      {/* For brevity, keeping original chat/queue/builder implementations */}
      {/* These would need similar styling updates */}

      {activeTab === 'chat' && (
        <div className="space-y-6">
          {/* ── No device selected ── */}
          {!selectedClient && (
            <div className="rounded-xl overflow-hidden"
                 style={{ background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)', boxShadow: '0 0 20px rgba(0, 229, 204, 0.1)' }}>
              <div className="p-8 text-center" style={{ color: 'var(--aimaru-text-dim)' }}>
                <div className="text-6xl mb-4">🤖</div>
                <h3 className="text-2xl font-bold mb-3 glow-text-cyan" style={{ color: 'var(--aimaru-cyan)' }}>
                  AI DEVICE ADMINISTRATION
                </h3>
                <p className="text-lg font-mono">
                  Select a connected device from the Overview tab to start an AI-powered administration session.
                </p>
              </div>
            </div>
          )}

          {/* ── Device selected, mode selector ── */}
          {selectedClient && !currentSession && (
            <div className="rounded-xl p-8"
                 style={{ background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)', boxShadow: '0 0 20px rgba(0, 229, 204, 0.1)' }}>
              <div className="text-center mb-8">
                <div className="text-5xl mb-3">🤖</div>
                <h3 className="text-2xl font-bold glow-text-cyan uppercase tracking-wide" style={{ color: 'var(--aimaru-cyan)' }}>
                  AI DEVICE ADMINISTRATION
                </h3>
                <p className="text-sm font-mono mt-2" style={{ color: 'var(--aimaru-text-dim)' }}>
                  Target: <span style={{ color: 'var(--aimaru-text)' }}>{selectedClient}</span>
                </p>
              </div>

              <div className="grid md:grid-cols-2 gap-4 max-w-2xl mx-auto mb-8">
                {/* Free Mode */}
                <button
                  onClick={() => setChatMode('free')}
                  className="p-5 rounded-xl text-left transition-all"
                  style={{
                    background: chatMode === 'free' ? 'rgba(0,229,204,0.12)' : 'rgba(0,0,0,0.3)',
                    border: `2px solid ${chatMode === 'free' ? 'var(--aimaru-cyan)' : 'var(--aimaru-dark-border)'}`,
                    boxShadow: chatMode === 'free' ? '0 0 20px rgba(0,229,204,0.2)' : 'none'
                  }}>
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-2xl">💬</span>
                    <div>
                      <p className="font-bold uppercase tracking-wide text-sm"
                         style={{ color: chatMode === 'free' ? 'var(--aimaru-cyan)' : 'var(--aimaru-text)' }}>
                        Free Mode
                      </p>
                      <p className="text-xs font-mono" style={{ color: 'var(--aimaru-text-dim)' }}>Standard AI chat</p>
                    </div>
                    {chatMode === 'free' && (
                      <span className="ml-auto text-xs font-bold px-2 py-0.5 rounded"
                            style={{ background: 'rgba(0,229,204,0.2)', color: 'var(--aimaru-cyan)', border: '1px solid var(--aimaru-cyan)' }}>
                        SELECTED
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-mono leading-relaxed" style={{ color: 'var(--aimaru-text-dim)' }}>
                    You drive the session. Ask the AI anything — it executes PowerShell on demand.
                    No structured flow, full flexibility.
                  </p>
                </button>

                {/* Guide Mode */}
                <button
                  onClick={() => setChatMode('guide')}
                  className="p-5 rounded-xl text-left transition-all"
                  style={{
                    background: chatMode === 'guide' ? 'rgba(239,68,68,0.1)' : 'rgba(0,0,0,0.3)',
                    border: `2px solid ${chatMode === 'guide' ? '#EF4444' : 'var(--aimaru-dark-border)'}`,
                    boxShadow: chatMode === 'guide' ? '0 0 20px rgba(239,68,68,0.2)' : 'none'
                  }}>
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-2xl">⚔️</span>
                    <div>
                      <p className="font-bold uppercase tracking-wide text-sm"
                         style={{ color: chatMode === 'guide' ? '#EF4444' : 'var(--aimaru-text)' }}>
                        MITRE ATT&CK Guide
                      </p>
                      <p className="text-xs font-mono" style={{ color: 'var(--aimaru-text-dim)' }}>Kill chain operator</p>
                    </div>
                    {chatMode === 'guide' && (
                      <span className="ml-auto text-xs font-bold px-2 py-0.5 rounded"
                            style={{ background: 'rgba(239,68,68,0.2)', color: '#EF4444', border: '1px solid #EF4444' }}>
                        SELECTED
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-mono leading-relaxed" style={{ color: 'var(--aimaru-text-dim)' }}>
                    AI guides you stage by stage through all 8 MITRE ATT&CK tactics.
                    Discovery → Privilege Escalation → Defense Evasion → Credentials → Persistence → Lateral Movement → Collection → Exfiltration.
                  </p>
                  <div className="flex flex-wrap gap-1 mt-3">
                    {['TA0007','TA0004','TA0005','TA0006','TA0003','TA0008','TA0009','TA0010'].map(id => (
                      <span key={id} className="text-xs font-mono px-1.5 py-0.5 rounded"
                            style={{ background: `${TACTIC_COLORS[id]}18`, border: `1px solid ${TACTIC_COLORS[id]}40`, color: TACTIC_COLORS[id], fontSize: '10px' }}>
                        {id}
                      </span>
                    ))}
                  </div>
                </button>
              </div>

              <div className="text-center">
                <button
                  onClick={() => startChatSession(chatMode)}
                  disabled={!selectedLLMConfig}
                  className="px-10 py-3 rounded-lg font-bold uppercase tracking-wide text-sm transition-all disabled:opacity-40"
                  style={{
                    background: chatMode === 'guide' ? 'rgba(239,68,68,0.2)' : 'rgba(0,229,204,0.2)',
                    border: `1px solid ${chatMode === 'guide' ? '#EF4444' : 'var(--aimaru-cyan)'}`,
                    color: chatMode === 'guide' ? '#EF4444' : 'var(--aimaru-cyan)'
                  }}
                  onMouseEnter={e => {
                    if (selectedLLMConfig) {
                      (e.currentTarget as HTMLElement).style.boxShadow = chatMode === 'guide'
                        ? '0 0 20px rgba(239,68,68,0.4)' : '0 0 20px rgba(0,229,204,0.4)'
                    }
                  }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.boxShadow = 'none' }}>
                  {chatMode === 'guide' ? '⚔️ START KILL CHAIN' : '🤖 START FREE SESSION'}
                </button>
                {!selectedLLMConfig && (
                  <p className="text-xs font-mono mt-2" style={{ color: '#EF4444' }}>
                    Configure an LLM in Settings → LLM first
                  </p>
                )}
              </div>
            </div>
          )}

          {selectedClient && currentSession && (
            <>
              {/* Chat Header */}
              <div className="rounded-xl p-5 scan-line"
                   style={{
                     background: chatMode === 'guide'
                       ? 'rgba(239, 68, 68, 0.18)'
                       : 'rgba(0, 229, 204, 0.15)',
                     border: `2px solid ${chatMode === 'guide' ? 'rgba(239,68,68,0.5)' : 'rgba(0,229,204,0.5)'}`,
                     boxShadow: chatMode === 'guide'
                       ? '0 0 30px rgba(239,68,68,0.25)'
                       : '0 0 30px rgba(0,229,204,0.25)'
                   }}>
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-2xl font-bold uppercase tracking-wide" style={{ color: 'var(--aimaru-cyan)', textShadow: '0 2px 8px rgba(0,0,0,0.5)' }}>
                      {chatMode === 'guide' ? '⚔️ MITRE ATT&CK KILL CHAIN' : '🤖 AI CHAT SESSION'}
                    </h2>
                    <p className="text-sm font-mono" style={{ color: '#DDD', textShadow: '0 1px 4px rgba(0,0,0,0.5)' }}>
                      Device: {selectedClient} | {chatMode === 'guide' ? 'Guide Mode — tactic by tactic' : 'Free Mode'} | Session: {currentSession?.substring(0, 8)}...
                    </p>
                    {/* LLM Model Info with Brand Logo */}
                    {(() => {
                      const session = chatSessions.find(s => s.id === currentSession)
                      const config = llmConfigs.find(c => c.id === session?.llm_config_id)
                      if (config) {
                        const providerLower = config.provider.toLowerCase()
                        const brandColors: Record<string, { bg: string, text: string, name: string }> = {
                          'anthropic': { bg: '#6B21A8', text: '#E879F9', name: 'Claude' },
                          'openai': { bg: '#10A37F', text: '#FFF', name: 'ChatGPT' },
                          'zhipu': { bg: '#1E40AF', text: '#93C5FD', name: 'GLM' },
                        }
                        const brand = brandColors[providerLower] || { bg: '#666', text: '#CCC', name: config.provider }
                        return (
                          <div className="flex items-center gap-3 mt-3">
                            <div style={{
                              background: brand.bg,
                              padding: '6px 10px',
                              borderRadius: '5px',
                              border: `1.5px solid ${brand.text}80`,
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
                              boxShadow: `0 0 12px ${brand.text}40`
                            }}>
                              <span style={{
                                width: '24px',
                                height: '24px',
                                borderRadius: '4px',
                                background: brand.text + '30',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: '12px',
                                fontWeight: 'bold',
                                color: brand.text,
                                border: `1px solid ${brand.text}50`
                              }}>
                                {brand.name.substring(0, 1)}
                              </span>
                              <div>
                                <div style={{ fontSize: '12px', fontWeight: '700', color: brand.text }}>
                                  {brand.name}
                                </div>
                                <div style={{ fontSize: '10px', fontWeight: '600', color: brand.text + 'BB', marginTop: '2px' }}>
                                  {config.model}
                                </div>
                              </div>
                            </div>
                          </div>
                        )
                      }
                      return null
                    })()}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => { setCurrentSession(null); setMessages([]) }}
                      className="px-3 py-1.5 rounded-md text-xs font-bold transition-all"
                      style={{ background: 'rgba(0,229,204,0.1)', border: '1px solid rgba(0,229,204,0.3)', color: 'var(--aimaru-cyan)' }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,229,204,0.2)' }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,229,204,0.1)' }}>
                      ↩ NEW SESSION
                    </button>
                    <button
                      onClick={() => { setSelectedClient(null); setCurrentSession(null); setMessages([]) }}
                      className="px-3 py-1.5 rounded-md text-xs font-bold transition-all"
                      style={{ background: 'rgba(0,229,204,0.1)', border: '1px solid rgba(0,229,204,0.3)', color: 'var(--aimaru-cyan)' }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,229,204,0.2)' }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,229,204,0.1)' }}>
                      ✕ CLOSE
                    </button>
                  </div>
                </div>
              </div>

              {/* ATT&CK Tactic Progress Bar — guide mode only */}
              {chatMode === 'guide' && (() => {
                const parsed = parseMessagesForTTPs(messages)
                const hoveredTactic = ATTACK_TACTICS.find(t => t.id === hoveredTacticId) ?? null
                return (
                  <div className="rounded-xl p-4"
                       style={{ background: 'var(--aimaru-dark-card)', border: '1px solid rgba(239,68,68,0.3)' }}>
                    <p className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: 'var(--aimaru-text-dim)' }}>
                      ATT&CK Kill Chain Progress
                    </p>

                    {/* Tactic cards row */}
                    <div className="flex gap-2 overflow-x-auto pb-1"
                         onMouseLeave={() => setHoveredTacticId(null)}>
                      {ATTACK_TACTICS.map(tactic => {
                        const status = getTacticStatus(tactic.id, parsed)
                        const discovered = tactic.techniques.filter(t => parsed.discoveredTechniques.has(t.id)).length
                        const isHovered = hoveredTacticId === tactic.id
                        const color = status === 'complete' ? '#10B981' : status === 'active' ? tactic.color : 'var(--aimaru-dark-border)'
                        const textColor = status === 'complete' ? '#10B981' : status === 'active' ? tactic.color : 'var(--aimaru-text-dim)'
                        return (
                          <button key={tactic.id}
                               onClick={() => jumpToTactic(tactic)}
                               disabled={!currentSession}
                               title={currentSession ? `Click to execute ${tactic.name}` : 'Start a guide session first'}
                               className="flex-shrink-0 px-3 py-2 rounded-lg text-left transition-all"
                               style={{
                                 background: isHovered
                                   ? (status === 'complete' ? 'rgba(16,185,129,0.22)' : `${tactic.color}28`)
                                   : (status === 'complete' ? 'rgba(16,185,129,0.12)' : status === 'active' ? `${tactic.color}18` : 'rgba(45,55,72,0.4)'),
                                 border: `1px solid ${isHovered ? tactic.color : color}`,
                                 boxShadow: isHovered ? `0 0 12px ${tactic.color}44` : 'none',
                                 minWidth: '108px',
                                 cursor: currentSession ? 'pointer' : 'default',
                                 transition: 'all 0.15s ease'
                               }}
                               onMouseEnter={() => setHoveredTacticId(tactic.id)}>
                            {/* ID row + technique count badge */}
                            <div className="flex items-center justify-between gap-1">
                              <div className="flex items-center gap-1 text-xs font-bold font-mono" style={{ color: textColor }}>
                                {status === 'complete' && <span>✓</span>}
                                {status === 'active' && <span>▶</span>}
                                <span>{tactic.id}</span>
                              </div>
                              <span style={{
                                fontSize: '8px', fontFamily: 'monospace', fontWeight: 700,
                                background: `${tactic.color}1a`,
                                color: status === 'complete' ? '#10B981' : tactic.color,
                                border: `1px solid ${tactic.color}44`,
                                borderRadius: '4px', padding: '1px 4px', flexShrink: 0
                              }}>
                                {tactic.techniques.length}
                              </span>
                            </div>

                            {/* Tactic name */}
                            <div className="font-mono mt-0.5" style={{ fontSize: '10px', color: textColor, opacity: 0.85 }}>
                              {tactic.name}
                            </div>

                            {/* Progress line — only when something discovered */}
                            {discovered > 0 && (
                              <div className="font-mono mt-1 flex items-center gap-1" style={{ fontSize: '9px', color: '#10B981', opacity: 0.8 }}>
                                <span>✓</span>
                                <span>{discovered}/{tactic.techniques.length} done</span>
                              </div>
                            )}
                          </button>
                        )
                      })}
                    </div>

                    {/* Technique inspector — appears below cards when a tactic is hovered */}
                    <div style={{
                      minHeight: '52px',
                      marginTop: hoveredTactic ? '10px' : '0',
                      paddingTop: hoveredTactic ? '8px' : '0',
                      borderTop: hoveredTactic ? `1px solid ${hoveredTactic?.color ?? 'transparent'}33` : '1px solid transparent',
                      transition: 'all 0.15s ease',
                      overflow: 'hidden'
                    }}>
                      {hoveredTactic ? (
                        <>
                          <p className="text-xs font-mono mb-2 flex items-center gap-2" style={{ color: hoveredTactic.color, opacity: 0.7 }}>
                            <span style={{ fontWeight: 700 }}>{hoveredTactic.id}</span>
                            <span style={{ opacity: 0.5 }}>·</span>
                            <span>{hoveredTactic.name}</span>
                            <span style={{ opacity: 0.5 }}>·</span>
                            <span style={{ opacity: 0.6 }}>hover techniques below — click card to execute</span>
                          </p>
                          <div className="flex flex-wrap gap-1.5">
                            {hoveredTactic.techniques.map(t => {
                              const isDone = parsed.discoveredTechniques.has(t.id)
                              return (
                                <span key={t.id} style={{
                                  display: 'inline-flex', alignItems: 'center', gap: '4px',
                                  fontSize: '9px', fontFamily: 'monospace',
                                  background: isDone ? 'rgba(16,185,129,0.1)' : `${hoveredTactic.color}0d`,
                                  border: `1px solid ${isDone ? '#10B981' : hoveredTactic.color}44`,
                                  borderRadius: '4px', padding: '2px 6px',
                                  color: isDone ? '#10B981' : hoveredTactic.color,
                                }}>
                                  {isDone && <span>✓</span>}
                                  <span style={{ opacity: 0.7 }}>{t.id}</span>
                                  <span style={{ color: 'var(--aimaru-text-dim)', opacity: 0.85 }}>{t.name}</span>
                                </span>
                              )
                            })}
                          </div>
                        </>
                      ) : (
                        <p className="text-xs font-mono" style={{ color: 'var(--aimaru-text-dim)', opacity: 0.4 }}>
                          Hover a tactic to inspect its techniques
                        </p>
                      )}
                    </div>
                  </div>
                )
              })()}

              {/* Chat Messages */}
              <div className="rounded-xl overflow-hidden"
                   style={{
                     background: 'var(--aimaru-dark-card)',
                     border: '1px solid var(--aimaru-dark-border)',
                     boxShadow: '0 0 20px rgba(0, 229, 204, 0.1)'
                   }}>
                <div className="h-[500px] overflow-y-auto p-6 space-y-4 messages-container">
                  {messages.length === 0 ? (
                    <div className="text-center py-12" style={{ color: 'var(--aimaru-text-dim)' }}>
                      <div className="text-4xl mb-3">💬</div>
                      <p className="font-mono">Start a conversation with the AI assistant</p>
                      <p className="text-sm mt-2">Ask questions or request actions on the device</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {messages.map((msg, idx) => {
                        // Only show progress spinner for ACTIVELY ONGOING operations
                        // (not for past operations shown in history)
                        const isProgressMsg = msg.role === 'system' && (
                          (msg.content?.includes('Creating') && idx === messages.length - 1) ||
                          (msg.content?.includes('Waiting') && idx === messages.length - 1) ||
                          (msg.content?.includes('Executing') && idx === messages.length - 1)
                        )

                        const getLLMIcon = () => {
                          const session = chatSessions.find(s => s.id === currentSession)
                          const config = llmConfigs.find(c => c.id === session?.llm_config_id)
                          if (!config) return '🤖'

                          const provider = config.provider.toLowerCase()
                          if (provider.includes('anthropic') || provider.includes('claude')) return '🧠'
                          if (provider.includes('openai') || provider.includes('gpt')) return '⚡'
                          if (provider.includes('glm') || provider.includes('zhipu')) return '✨'
                          return '🤖'
                        }

                        const animationDelay = idx * 80

                        return (
                          <div
                            key={msg.id}
                            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} message-animate`}
                            style={{ animationDelay: `${animationDelay}ms` }}
                          >
                            <div
                              className={`max-w-[85%] rounded-lg overflow-hidden transition-all ${
                                msg.role === 'user' ? 'rounded-tr-none' : 'rounded-tl-none'
                              }`}
                              style={{
                                background: msg.role === 'user'
                                  ? 'rgba(0, 229, 204, 0.12)'
                                  : msg.role === 'tool'
                                  ? 'rgba(168, 85, 247, 0.1)'
                                  : msg.role === 'system'
                                  ? 'rgba(100, 150, 200, 0.08)'
                                  : 'rgba(168, 85, 247, 0.08)',
                                border: `1px solid ${
                                  msg.role === 'user'
                                    ? 'rgba(0, 229, 204, 0.35)'
                                    : msg.role === 'tool'
                                    ? 'rgba(168, 85, 247, 0.35)'
                                    : msg.role === 'system'
                                    ? 'rgba(100, 150, 200, 0.25)'
                                    : 'rgba(168, 85, 247, 0.3)'
                                }`,
                                boxShadow: msg.role === 'user'
                                  ? '0 0 15px rgba(0, 229, 204, 0.15)'
                                  : msg.role === 'tool'
                                  ? '0 0 15px rgba(168, 85, 247, 0.12)'
                                  : 'none'
                              }}
                            >
                              {/* Professional Header */}
                              <div
                                className="px-4 pt-3 pb-2.5 flex items-center gap-3 border-b"
                                style={{
                                  borderColor: 'rgba(0, 229, 204, 0.2)',
                                  background: 'rgba(0, 229, 204, 0.08)'
                                }}
                              >
                                <span className="text-lg font-bold">
                                  {msg.role === 'user' ? '👤' : msg.role === 'tool' ? '⚙️' : getLLMIcon()}
                                </span>
                                <span
                                  className="font-bold text-xs uppercase tracking-widest flex-1"
                                  style={{ color: msg.role === 'user' ? 'var(--aimaru-cyan)' : '#A855F7' }}
                                >
                                  {msg.role === 'tool' ? `${msg.tool_name}` : msg.role.toUpperCase()}
                                </span>
                                {isProgressMsg && <span className="progress-spinner"></span>}
                                <span
                                  className="text-xs font-mono"
                                  style={{ color: 'var(--aimaru-text-dim)' }}
                                >
                                  {new Date(msg.created_at).toLocaleTimeString()}
                                </span>
                              </div>

                              {/* Message Content */}
                              <div
                                className="px-4 py-3 text-sm whitespace-pre-wrap font-mono"
                                style={{ color: 'var(--aimaru-text)' }}
                              >
                                {msg.content}
                              </div>

                              {/* Tool Arguments */}
                              {msg.tool_args && (
                                <details className="px-4 pb-3 text-xs">
                                  <summary
                                    className="cursor-pointer font-bold uppercase tracking-wide hover:text-cyan-300"
                                    style={{ color: 'var(--aimaru-cyan)' }}
                                  >
                                    ▶ Arguments
                                  </summary>
                                  <pre
                                    className="mt-2 p-2 rounded overflow-auto font-mono text-xs"
                                    style={{
                                      background: 'rgba(0, 0, 0, 0.4)',
                                      color: 'var(--aimaru-cyan)',
                                      border: '1px solid rgba(0, 229, 204, 0.25)'
                                    }}
                                  >
                                    {msg.tool_args}
                                  </pre>
                                </details>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>

                {/* Message Input */}
                <div className="border-t p-4"
                     style={{ borderColor: 'var(--aimaru-dark-border)' }}>
                  <div className="flex gap-3">
                    <input
                      type="text"
                      value={newMessage}
                      onChange={(e) => setNewMessage(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          sendChatMessage()
                        }
                      }}
                      placeholder={chatMode === 'guide' ? 'Type "next" to advance to next tactic, or give a directive…' : 'Ask the AI to help you manage this device...'}
                      disabled={sendingMessage}
                      className="flex-1 px-4 py-3 rounded-lg text-sm font-mono focus:outline-none transition-all"
                      style={{
                        background: 'var(--aimaru-dark-surface)',
                        border: '1px solid var(--aimaru-dark-border)',
                        color: 'var(--aimaru-text)'
                      }}
                    />
                    <button
                      onClick={sendChatMessage}
                      disabled={sendingMessage || !newMessage.trim()}
                      className="px-6 py-3 rounded-lg font-bold transition-all disabled:opacity-50"
                      style={{
                        background: 'rgba(0, 229, 204, 0.2)',
                        border: '1px solid var(--aimaru-cyan)',
                        color: 'var(--aimaru-cyan)'
                      }}
                      onMouseEnter={(e) => {
                        if (!sendingMessage && newMessage.trim()) {
                          e.currentTarget.style.background = 'rgba(0, 229, 204, 0.3)'
                          e.currentTarget.style.boxShadow = '0 0 20px rgba(0, 229, 204, 0.5)'
                        }
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(0, 229, 204, 0.2)'
                        e.currentTarget.style.boxShadow = 'none'
                      }}
                    >
                      {sendingMessage ? (
                        <span className="flex items-center gap-2">
                          <div className="cyber-loading"></div>
                          SENDING
                        </span>
                      ) : (
                        '📤 SEND'
                      )}
                    </button>
                  </div>
                  <div className="mt-2 text-xs font-mono" style={{ color: 'var(--aimaru-text-dim)' }}>
                    Press Enter to send • Shift+Enter for new line
                  </div>
                </div>
              </div>

              {/* Direct Commands Panel */}
              <div className="rounded-xl p-6"
                   style={{
                     background: 'var(--aimaru-dark-card)',
                     border: '1px solid var(--aimaru-dark-border)',
                     boxShadow: '0 0 20px rgba(0, 229, 204, 0.05)'
                   }}>
                <button
                  onClick={() => setShowDirectCommands(!showDirectCommands)}
                  className="w-full flex items-center justify-between font-bold text-lg mb-4 transition-all"
                  style={{ color: 'var(--aimaru-cyan)' }}
                >
                  <span className="uppercase tracking-wide">⚡ DIRECT POWERSHELL COMMANDS</span>
                  <span>{showDirectCommands ? '▼' : '▶'}</span>
                </button>

                {showDirectCommands && (
                  <div className="space-y-4">
                    <div className="flex gap-2 border-b pb-3"
                         style={{ borderColor: 'var(--aimaru-dark-border)' }}>
                      {[
                        { id: 'command', label: '💻 Single Command' },
                        { id: 'editor', label: '📝 Script Editor' },
                        { id: 'upload', label: '📁 Upload Script' }
                      ].map((mode) => (
                        <button
                          key={mode.id}
                          onClick={() => setScriptMode(mode.id as any)}
                          className={`px-4 py-2 rounded-md text-sm font-bold transition-all ${
                            scriptMode === mode.id ? 'glow-cyan' : ''
                          }`}
                          style={{
                            background: scriptMode === mode.id
                              ? 'rgba(0, 229, 204, 0.2)'
                              : 'rgba(160, 174, 192, 0.1)',
                            border: `1px solid ${
                              scriptMode === mode.id
                                ? 'var(--aimaru-cyan)'
                                : 'var(--aimaru-dark-border)'
                            }`,
                            color: scriptMode === mode.id
                              ? 'var(--aimaru-cyan)'
                              : 'var(--aimaru-text)'
                          }}
                        >
                          {mode.label}
                        </button>
                      ))}
                    </div>

                    {scriptMode === 'command' && (
                      <div>
                        <label className="block text-sm font-bold mb-2 uppercase tracking-wide"
                               style={{ color: 'var(--aimaru-text)' }}>
                          PowerShell Command
                        </label>
                        <input
                          type="text"
                          value={directCommand}
                          onChange={(e) => setDirectCommand(e.target.value)}
                          placeholder="Get-Process | Select-Object -First 10"
                          className="w-full px-4 py-3 rounded-lg font-mono text-sm focus:outline-none"
                          style={{
                            background: 'var(--aimaru-dark-surface)',
                            border: '1px solid var(--aimaru-dark-border)',
                            color: 'var(--aimaru-text)'
                          }}
                        />
                      </div>
                    )}

                    {scriptMode === 'editor' && (
                      <div>
                        <label className="block text-sm font-bold mb-2 uppercase tracking-wide"
                               style={{ color: 'var(--aimaru-text)' }}>
                          PowerShell Script
                        </label>
                        <textarea
                          value={scriptContent}
                          onChange={(e) => setScriptContent(e.target.value)}
                          placeholder="# Multi-line PowerShell script&#10;Get-Service | Where-Object Status -eq 'Running'"
                          rows={8}
                          className="w-full px-4 py-3 rounded-lg font-mono text-sm focus:outline-none"
                          style={{
                            background: 'var(--aimaru-dark-surface)',
                            border: '1px solid var(--aimaru-dark-border)',
                            color: 'var(--aimaru-text)'
                          }}
                        />
                      </div>
                    )}

                    {scriptMode === 'upload' && (
                      <div>
                        <label className="block text-sm font-bold mb-2 uppercase tracking-wide"
                               style={{ color: 'var(--aimaru-text)' }}>
                          Upload PowerShell Script (.ps1, .txt)
                        </label>
                        <input
                          type="file"
                          accept=".ps1,.txt"
                          onChange={handleFileUpload}
                          className="w-full px-4 py-3 rounded-lg text-sm focus:outline-none"
                          style={{
                            background: 'var(--aimaru-dark-surface)',
                            border: '1px solid var(--aimaru-dark-border)',
                            color: 'var(--aimaru-text)'
                          }}
                        />
                        {scriptFile && (
                          <div className="mt-2 text-sm font-mono"
                               style={{ color: 'var(--aimaru-cyan)' }}>
                            📄 {scriptFile.name}
                          </div>
                        )}
                      </div>
                    )}

                    <button
                      onClick={executeScript}
                      disabled={executingScript}
                      className="w-full px-6 py-3 rounded-lg font-bold transition-all disabled:opacity-50"
                      style={{
                        background: 'rgba(168, 85, 247, 0.2)',
                        border: '1px solid #A855F7',
                        color: '#A855F7'
                      }}
                      onMouseEnter={(e) => {
                        if (!executingScript) {
                          e.currentTarget.style.background = 'rgba(168, 85, 247, 0.3)'
                          e.currentTarget.style.boxShadow = '0 0 20px rgba(168, 85, 247, 0.5)'
                        }
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(168, 85, 247, 0.2)'
                        e.currentTarget.style.boxShadow = 'none'
                      }}
                    >
                      {executingScript ? (
                        <span className="flex items-center justify-center gap-2">
                          <div className="cyber-loading"></div>
                          EXECUTING...
                        </span>
                      ) : (
                        '⚡ EXECUTE ON DEVICE'
                      )}
                    </button>

                    {scriptResult && (
                      <div className="rounded-lg p-4 glow-cyan"
                           style={{
                             background: '#000',
                             border: '1px solid var(--aimaru-cyan)',
                             boxShadow: '0 0 20px rgba(0, 229, 204, 0.3)'
                           }}>
                        <div className="font-bold text-sm mb-2 uppercase tracking-wide"
                             style={{ color: 'var(--aimaru-cyan)' }}>
                          📊 EXECUTION RESULT
                        </div>
                        <pre className="text-sm font-mono whitespace-pre-wrap overflow-auto max-h-64"
                             style={{ color: '#10B981' }}>
                          {scriptResult}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {activeTab === 'queue' && (
        <div className="rounded-xl p-5"
             style={{
               background: 'rgba(0, 229, 204, 0.15)',
               border: '2px solid rgba(0,229,204,0.5)',
               boxShadow: '0 0 30px rgba(0,229,204,0.25)'
             }}>
          <h2 className="text-xl font-bold mb-4 uppercase tracking-wide"
              style={{ color: 'var(--aimaru-cyan)', textShadow: '0 2px 8px rgba(0,0,0,0.5)' }}>
            📋 INSTRUCTION QUEUE
            {selectedClient && (
              <span className="text-sm font-normal ml-3" style={{ color: 'var(--aimaru-text-dim)' }}>
                (Filtered: {selectedClient})
              </span>
            )}
          </h2>

          <div className="overflow-x-auto">
            <table className="w-full text-sm font-mono">
              <thead>
                <tr className="text-left border-b" style={{ borderColor: 'var(--aimaru-dark-border)' }}>
                  <th className="py-3 pr-4 font-bold uppercase" style={{ color: 'var(--aimaru-cyan)' }}>Client</th>
                  <th className="py-3 pr-4 font-bold uppercase" style={{ color: 'var(--aimaru-cyan)' }}>Status</th>
                  <th className="py-3 pr-4 font-bold uppercase" style={{ color: 'var(--aimaru-cyan)' }}>Created</th>
                  <th className="py-3 pr-4 font-bold uppercase" style={{ color: 'var(--aimaru-cyan)' }}>Command</th>
                  <th className="py-3 pr-4 font-bold uppercase" style={{ color: 'var(--aimaru-cyan)' }}>Result</th>
                </tr>
              </thead>
              <tbody>
                {queue
                  .filter(item => !selectedClient || item.client_id === selectedClient)
                  .map((item) => (
                  <tr key={item.id} className="border-b transition-all hover:bg-opacity-50"
                      style={{
                        borderColor: 'var(--aimaru-dark-border)',
                        color: 'var(--aimaru-text)'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'rgba(0, 229, 204, 0.05)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'transparent'
                      }}>
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <span className="font-bold">{item.client_id}</span>
                        {!clients.find(c => c.id === item.client_id)?.connected && (
                          <span className="px-2 py-0.5 rounded text-xs font-bold uppercase"
                                style={{
                                  background: 'rgba(160, 174, 192, 0.2)',
                                  border: '1px solid var(--aimaru-gray)',
                                  color: 'var(--aimaru-text-dim)'
                                }}
                                title="Client offline - results cannot be decrypted">
                            OFFLINE
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 pr-4">
                      <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase ${
                        item.status === 'completed' ? 'badge-completed' :
                        item.status === 'delivered' ? 'badge-delivered' :
                        'badge-queued'
                      }`}>
                        {item.status}
                      </span>
                    </td>
                    <td className="py-3 pr-4" style={{ color: 'var(--aimaru-text-dim)' }}>
                      {new Date(item.created_at).toLocaleString()}
                    </td>
                    <td className="py-3 pr-4 max-w-md truncate" title={item.command_plain}>
                      <code className="text-xs px-2 py-1 rounded"
                            style={{
                              background: 'rgba(0, 229, 204, 0.1)',
                              color: 'var(--aimaru-cyan)'
                            }}>
                        {item.command_plain}
                      </code>
                    </td>
                    <td className="py-3 pr-4">
                      {item.status === 'completed' ? (
                        <button
                          onClick={() => viewResult(item.id)}
                          disabled={resultLoading}
                          className="underline text-xs font-bold transition-all disabled:opacity-50"
                          style={{ color: 'var(--aimaru-cyan)' }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.textShadow = '0 0 10px rgba(0, 229, 204, 0.8)'
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.textShadow = 'none'
                          }}
                        >
                          {resultLoading ? 'LOADING...' : '📋 VIEW'}
                        </button>
                      ) : (
                        <span className="text-xs" style={{ color: 'var(--aimaru-text-dim)' }}>—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {queue.filter(item => !selectedClient || item.client_id === selectedClient).length === 0 && (
              <div className="text-center py-12 font-mono" style={{ color: 'var(--aimaru-text-dim)' }}>
                <div className="text-4xl mb-3">📋</div>
                No instructions found
                {selectedClient && ` for ${selectedClient}`}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'builder' && (
        <MCPClientBuilder />
      )}

      {activeTab === 'tools' && (
        <div className="space-y-6">
          {/* Header */}
          <div className="rounded-xl p-5"
               style={{
                 background: 'rgba(168, 85, 247, 0.15)',
                 border: '2px solid rgba(168,85,247,0.5)',
                 boxShadow: '0 0 30px rgba(168,85,247,0.25)'
               }}>
            <h2 className="text-2xl font-bold uppercase tracking-wider"
                style={{ color: '#D8B4FE', textShadow: '0 2px 8px rgba(0,0,0,0.5)' }}>
              ⚡ PREDEFINED TOOLS
            </h2>
            <p className="text-sm font-mono" style={{ color: '#D8B4FE', textShadow: '0 1px 4px rgba(0,0,0,0.5)', marginTop: '8px' }}>
              Pre-configured security tools with PowerShell script generation
            </p>
          </div>

          {/* Tools Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* AMSI_BP Tool */}
            <div className="rounded-xl p-6 transition-all hover:shadow-2xl"
                 style={{
                   background: 'var(--aimaru-dark-card)',
                   border: '1px solid #DC2626',
                   boxShadow: '0 0 20px rgba(220, 38, 38, 0.1)'
                 }}
                 onMouseEnter={(e) => {
                   e.currentTarget.style.borderColor = '#DC2626'
                   e.currentTarget.style.boxShadow = '0 0 30px rgba(220, 38, 38, 0.3)'
                 }}
                 onMouseLeave={(e) => {
                   e.currentTarget.style.borderColor = '#DC2626'
                   e.currentTarget.style.boxShadow = '0 0 20px rgba(220, 38, 38, 0.1)'
                 }}>
              <div className="flex items-start gap-4 mb-4">
                <div className="text-4xl">🛡️</div>
                <div className="flex-1">
                  <h3 className="text-xl font-bold mb-2 uppercase tracking-wide"
                      style={{ color: '#DC2626' }}>
                    AMSI_BP
                  </h3>
                  <p className="text-sm font-mono mb-4" style={{ color: 'var(--aimaru-text-dim)' }}>
                    Advanced multi-level obfuscated PowerShell scripts for AMSI bypass using memory patching and provider enumeration.
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                <div className="p-3 rounded-lg" style={{ background: 'rgba(220, 38, 38, 0.1)' }}>
                  <p className="text-xs font-mono mb-2" style={{ color: 'var(--aimaru-text-dim)' }}>
                    Features:
                  </p>
                  <ul className="text-xs font-mono space-y-1" style={{ color: 'var(--aimaru-text)' }}>
                    <li>• Memory patching techniques</li>
                    <li>• Provider enumeration & patching</li>
                    <li>• Multi-level obfuscation (Base64/Advanced/Elite)</li>
                    <li>• Variable & function name randomization</li>
                    <li>• XOR encryption (Elite mode)</li>
                    <li>• ETW patching support</li>
                    <li>• Direct deployment to MCP clients</li>
                  </ul>
                </div>

                <a
                  href="/amsi"
                  className="block w-full px-4 py-3 rounded-lg font-bold text-center transition-all"
                  style={{
                    background: 'rgba(220, 38, 38, 0.2)',
                    border: '1px solid #DC2626',
                    color: '#DC2626',
                    textDecoration: 'none'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(220, 38, 38, 0.3)'
                    e.currentTarget.style.boxShadow = '0 0 20px rgba(220, 38, 38, 0.5)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'rgba(220, 38, 38, 0.2)'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                >
                  🚀 OPEN AMSI_BP DEPLOYMENT
                </a>
              </div>
            </div>

            {/* AI CLI Search Tool */}
            <div className="rounded-xl p-6 transition-all hover:shadow-2xl"
                 style={{
                   background: 'var(--aimaru-dark-card)',
                   border: '1px solid var(--aimaru-dark-border)',
                   boxShadow: '0 0 20px rgba(168, 85, 247, 0.05)'
                 }}
                 onMouseEnter={(e) => {
                   e.currentTarget.style.borderColor = 'var(--aimaru-purple)'
                   e.currentTarget.style.boxShadow = '0 0 30px rgba(168, 85, 247, 0.2)'
                 }}
                 onMouseLeave={(e) => {
                   e.currentTarget.style.borderColor = 'var(--aimaru-dark-border)'
                   e.currentTarget.style.boxShadow = '0 0 20px rgba(168, 85, 247, 0.05)'
                 }}>
              <div className="flex items-start gap-4 mb-4">
                <div className="text-4xl">🔍</div>
                <div className="flex-1">
                  <h3 className="text-xl font-bold mb-2 uppercase tracking-wide"
                      style={{ color: 'var(--aimaru-purple)' }}>
                    AI CLI Search
                  </h3>
                  <p className="text-sm font-mono mb-4" style={{ color: 'var(--aimaru-text-dim)' }}>
                    Advanced command-line interface search using AI-powered pattern recognition and intelligent filtering.
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                <div className="p-3 rounded-lg" style={{ background: 'rgba(168, 85, 247, 0.07)' }}>
                  <p className="text-xs font-mono mb-2" style={{ color: 'var(--aimaru-text-dim)' }}>
                    Features:
                  </p>
                  <ul className="text-xs font-mono space-y-1" style={{ color: 'var(--aimaru-text)' }}>
                    <li>• Discover AI runtimes on connected clients</li>
                    <li>• Interact with local models via C2 channel</li>
                    <li>• Pull, remove and inspect models remotely</li>
                    <li>• Supports Ollama, LM Studio, HuggingFace CLI</li>
                  </ul>
                </div>

                <a
                  href="/ai-modules"
                  className="block w-full px-4 py-3 rounded-lg font-bold text-center transition-all"
                  style={{
                    background: 'rgba(168, 85, 247, 0.2)',
                    border: '1px solid var(--aimaru-purple)',
                    color: 'var(--aimaru-purple)',
                    textDecoration: 'none'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(168, 85, 247, 0.3)'
                    e.currentTarget.style.boxShadow = '0 0 20px rgba(168, 85, 247, 0.5)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'rgba(168, 85, 247, 0.2)'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                >
                  🤖 OPEN AI MODULES
                </a>
              </div>
            </div>
          </div>

          {/* Generated Script Modal */}
          {generatedToolScript && (
            <div className="rounded-xl p-6"
                 style={{
                   background: 'var(--aimaru-dark-card)',
                   border: '1px solid var(--aimaru-cyan)',
                   boxShadow: '0 0 30px rgba(0, 229, 204, 0.3)'
                 }}>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-bold uppercase tracking-wide"
                    style={{ color: 'var(--aimaru-cyan)' }}>
                  📄 Generated Script: {toolScriptName}
                </h3>
                <button
                  onClick={() => setGeneratedToolScript(null)}
                  className="text-2xl transition-all"
                  style={{ color: 'var(--aimaru-text-dim)' }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = 'var(--aimaru-cyan)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = 'var(--aimaru-text-dim)'
                  }}
                >
                  ✕
                </button>
              </div>

              {/* Action Buttons */}
              <div className="flex gap-3 mb-4">
                <button
                  onClick={downloadToolScript}
                  className="px-4 py-2 rounded-lg font-bold transition-all"
                  style={{
                    background: 'rgba(0, 229, 204, 0.2)',
                    border: '1px solid var(--aimaru-cyan)',
                    color: 'var(--aimaru-cyan)'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(0, 229, 204, 0.3)'
                    e.currentTarget.style.boxShadow = '0 0 15px rgba(0, 229, 204, 0.5)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'rgba(0, 229, 204, 0.2)'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                >
                  📥 DOWNLOAD
                </button>
                <button
                  onClick={copyToolScriptToClipboard}
                  className="px-4 py-2 rounded-lg font-bold transition-all"
                  style={{
                    background: 'rgba(168, 85, 247, 0.2)',
                    border: '1px solid var(--aimaru-purple)',
                    color: 'var(--aimaru-purple)'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(168, 85, 247, 0.3)'
                    e.currentTarget.style.boxShadow = '0 0 15px rgba(168, 85, 247, 0.5)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'rgba(168, 85, 247, 0.2)'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                >
                  📋 COPY TO CLIPBOARD
                </button>
              </div>

              {/* Script Preview */}
              <div className="rounded-lg p-4 overflow-auto max-h-96 font-mono text-xs"
                   style={{
                     background: '#000',
                     border: '1px solid var(--aimaru-cyan)',
                     color: '#10B981'
                   }}>
                <pre className="whitespace-pre-wrap">{generatedToolScript}</pre>
              </div>

              {/* Usage Instructions */}
              {toolUsageInstructions && (
                <div className="mt-4 p-4 rounded-lg"
                     style={{
                       background: 'rgba(255, 193, 7, 0.1)',
                       border: '1px solid #FBB036'
                     }}>
                  <div className="font-bold text-sm mb-2 uppercase tracking-wide"
                       style={{ color: '#FBB036' }}>
                    📖 USAGE INSTRUCTIONS
                  </div>
                  <pre className="text-xs font-mono whitespace-pre-wrap"
                       style={{ color: 'var(--aimaru-text)' }}>
                    {toolUsageInstructions}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Info Panel */}
          <div className="rounded-xl p-6"
               style={{
                 background: 'var(--aimaru-dark-card)',
                 border: '1px solid var(--aimaru-dark-border)',
                 boxShadow: '0 0 20px rgba(255, 193, 7, 0.05)'
               }}>
            <div className="flex items-start gap-3">
              <div className="text-2xl">ℹ️</div>
              <div>
                <h4 className="font-bold mb-2 uppercase tracking-wide"
                    style={{ color: 'var(--aimaru-text)' }}>
                  About Predefined Tools
                </h4>
                <p className="text-sm font-mono" style={{ color: 'var(--aimaru-text-dim)' }}>
                  These tools generate ready-to-use PowerShell scripts for common security testing scenarios.
                  Each tool is pre-configured with best practices and can be customized before deployment.
                  Use responsibly and only in authorized testing environments.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      <ResultModal />
    </div>
  )
}
