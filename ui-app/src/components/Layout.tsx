import React, { PropsWithChildren, useState } from 'react'
import { Nav } from './Nav'

export function Layout({ children }: PropsWithChildren) {
  const [showAbout, setShowAbout] = useState(false)

  return (
    <div className="min-h-screen hex-pattern" style={{ background: 'var(--aimaru-dark-bg)' }}>
      <header className="border-b sticky top-0 z-10 scan-line"
              style={{
                background: 'var(--aimaru-dark-surface)',
                borderColor: 'var(--aimaru-dark-border)',
                boxShadow: '0 0 20px rgba(0, 229, 204, 0.1)'
              }}>
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center gap-6">
          <div className="flex items-center gap-3 cursor-pointer transition-all"
               onClick={() => setShowAbout(true)}
               onMouseEnter={(e) => {
                 e.currentTarget.style.transform = 'scale(1.05)'
               }}
               onMouseLeave={(e) => {
                 e.currentTarget.style.transform = 'scale(1)'
               }}
               title="Click to learn more about AIMARU">
            <img
              src="/aimaru-logo.png"
              alt="Aimaru"
              className="object-contain glow-cyan"
              style={{
                height: '105.6px',
                width: '105.6px',
                filter: 'drop-shadow(0 0 10px rgba(0, 229, 204, 0.5))'
              }}
            />
            <div>
              <h1 className="text-2xl font-bold glow-text-cyan" style={{ color: 'var(--aimaru-cyan)' }}>
                AIMARU
              </h1>
              <p className="text-xs tracking-wider" style={{ color: 'var(--aimaru-text-dim)' }}>
                AI C2 MCP PROJECT
              </p>
            </div>
          </div>
          <Nav />
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>

      {/* About Modal */}
      {showAbout && (
        <div className="fixed inset-0 flex items-center justify-center z-50 p-4"
             style={{ background: 'rgba(10, 14, 26, 0.95)' }}
             onClick={() => setShowAbout(false)}>
          <div className="rounded-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto glow-cyan-strong animate-fadeIn"
               style={{
                 background: 'var(--aimaru-dark-surface)',
                 border: '2px solid var(--aimaru-cyan)',
                 boxShadow: '0 0 40px rgba(0, 229, 204, 0.4)'
               }}
               onClick={(e) => e.stopPropagation()}>

            {/* Header with gradient */}
            <div className="p-6 text-center scan-line"
                 style={{
                   background: 'linear-gradient(135deg, var(--aimaru-cyan), #A855F7)',
                   boxShadow: '0 0 30px rgba(0, 229, 204, 0.3)'
                 }}>
              <img
                src="/aimaru-logo.png"
                alt="Aimaru Logo"
                className="mx-auto glow-cyan"
                style={{
                  height: '300px',
                  width: '300px',
                  filter: 'drop-shadow(0 0 20px rgba(255, 255, 255, 0.8))'
                }}
              />
              <h2 className="text-3xl font-bold mt-4 uppercase tracking-wider"
                  style={{ color: '#FFF', textShadow: '0 0 20px rgba(0, 229, 204, 0.8)' }}>
                AIMARU
              </h2>
              <p className="text-sm font-mono mt-2 opacity-90" style={{ color: '#FFF' }}>
                AI-Powered Command & Control MCP Platform
              </p>
            </div>

            {/* Content */}
            <div className="p-6 space-y-4">
              {/* Project Description */}
              <div>
                <h3 className="text-sm font-bold mb-2 uppercase tracking-wide"
                    style={{ color: 'var(--aimaru-cyan)' }}>
                  📋 About The Project
                </h3>
                <p className="text-xs font-mono leading-relaxed" style={{ color: 'var(--aimaru-text)' }}>
                  AIMARU is an advanced AI-powered Command & Control (C2) platform built on the Model Context Protocol (MCP).
                  It provides secure, encrypted communication channels for remote device management with intelligent automation
                  through LLM integration. Features include real-time client monitoring, PowerShell execution, AI-assisted
                  administration, and predefined security tools for penetration testing workflows.
                </p>
              </div>

              {/* Key Features */}
              <div>
                <h3 className="text-sm font-bold mb-2 uppercase tracking-wide"
                    style={{ color: 'var(--aimaru-purple)' }}>
                  ⚡ Key Features
                </h3>
                <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                  {[
                    '🔐 End-to-End Encryption',
                    '🤖 AI Chat Administration',
                    '🧠 Multi-Step Auto-Iteration',
                    '📈 Complexity Escalation (5 Levels)',
                    '⚙️ MCP Client Builder',
                    '🛡️ AMSI Bypass Generator',
                    '📊 Real-time Monitoring',
                    '🔧 PowerShell Integration',
                    '🎯 Failed Command Tracking',
                    '🔄 Session-Scoped Memory',
                    '⚡ LOLBins Integration',
                    '🛠️ Security Tools Generator'
                  ].map((feature, i) => (
                    <div key={i} className="p-2 rounded-lg transition-all"
                         style={{
                           background: 'rgba(0, 229, 204, 0.05)',
                           border: '1px solid var(--aimaru-dark-border)'
                         }}>
                      {feature}
                    </div>
                  ))}
                </div>
              </div>

              {/* New: Enhanced AI Capabilities */}
              <div>
                <h3 className="text-sm font-bold mb-2 uppercase tracking-wide"
                    style={{ color: 'var(--aimaru-cyan)' }}>
                  🚀 Enhanced AI Capabilities
                </h3>
                <div className="space-y-2 text-xs font-mono" style={{ color: 'var(--aimaru-text)' }}>
                  <div className="p-2 rounded-lg"
                       style={{
                         background: 'rgba(0, 229, 204, 0.05)',
                         border: '1px solid var(--aimaru-dark-border)'
                       }}>
                    <span className="font-bold" style={{ color: 'var(--aimaru-cyan)' }}>Multi-Step Auto-Iteration:</span> Up to 5 automatic retry attempts with intelligent learning from failures. Never repeats failed commands.
                  </div>
                  <div className="p-2 rounded-lg"
                       style={{
                         background: 'rgba(0, 229, 204, 0.05)',
                         border: '1px solid var(--aimaru-dark-border)'
                       }}>
                    <span className="font-bold" style={{ color: 'var(--aimaru-cyan)' }}>Complexity Escalation:</span> Automatic progression from PowerShell cmdlets → WMI → Registry → LOLBins → Scripts. Each level more advanced than the last.
                  </div>
                  <div className="p-2 rounded-lg"
                       style={{
                         background: 'rgba(0, 229, 204, 0.05)',
                         border: '1px solid var(--aimaru-dark-border)'
                       }}>
                    <span className="font-bold" style={{ color: 'var(--aimaru-cyan)' }}>Session Memory:</span> AI remembers conversation context and previous failures within each session for smarter command generation.
                  </div>
                  <div className="p-2 rounded-lg"
                       style={{
                         background: 'rgba(0, 229, 204, 0.05)',
                         border: '1px solid var(--aimaru-dark-border)'
                       }}>
                    <span className="font-bold" style={{ color: 'var(--aimaru-cyan)' }}>Transparent Progress:</span> Real-time "Attempt X/5" indicators show AI thinking and escalation strategy.
                  </div>
                </div>
              </div>

              {/* Credits */}
              <div className="p-3 rounded-lg"
                   style={{
                     background: 'rgba(168, 85, 247, 0.1)',
                     border: '1px solid var(--aimaru-purple)'
                   }}>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide"
                       style={{ color: 'var(--aimaru-purple)' }}>
                      Created By
                    </p>
                    <p className="text-lg font-bold mt-1 glow-text-cyan"
                       style={{ color: 'var(--aimaru-cyan)' }}>
                      WolfMneo
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-bold uppercase tracking-wide"
                       style={{ color: 'var(--aimaru-text-dim)' }}>
                      Year
                    </p>
                    <p className="text-lg font-bold mt-1"
                       style={{ color: 'var(--aimaru-cyan)' }}>
                      2025
                    </p>
                  </div>
                </div>
              </div>

              {/* GitHub Link - Placeholder for future */}
              <div className="p-3 rounded-lg text-center"
                   style={{
                     background: 'rgba(0, 229, 204, 0.1)',
                     border: '1px solid var(--aimaru-cyan)'
                   }}>
                <p className="text-xs font-mono mb-1" style={{ color: 'var(--aimaru-text-dim)' }}>
                  Open Source Repository
                </p>
                <a href="https://github.com/WolfMneo/aimaru-mcp"
                   target="_blank"
                   rel="noopener noreferrer"
                   className="text-xs font-bold font-mono hover:underline transition-all"
                   style={{ color: 'var(--aimaru-cyan)' }}
                   onMouseEnter={(e) => {
                     e.currentTarget.style.textShadow = '0 0 10px rgba(0, 229, 204, 0.8)'
                   }}
                   onMouseLeave={(e) => {
                     e.currentTarget.style.textShadow = 'none'
                   }}>
                  🔗 GitHub.com/WolfMneo/aimaru-mcp
                </a>
                <p className="text-xs font-mono mt-1" style={{ color: 'var(--aimaru-text-dim)' }}>
                  (Update this URL with your actual repository)
                </p>
              </div>

              {/* Security Notice */}
              <div className="p-2 rounded-lg"
                   style={{
                     background: 'rgba(251, 191, 36, 0.1)',
                     border: '1px solid #FBB036'
                   }}>
                <div className="flex items-start gap-2">
                  <span className="text-sm">⚠️</span>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wide mb-1"
                       style={{ color: '#FBB036' }}>
                      Security Notice
                    </p>
                    <p className="text-xs font-mono" style={{ color: 'var(--aimaru-text)' }}>
                      This platform is designed for authorized security testing and system administration only.
                      Use responsibly and in compliance with applicable laws and regulations.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t flex justify-end"
                 style={{ borderColor: 'var(--aimaru-dark-border)' }}>
              <button
                onClick={() => setShowAbout(false)}
                className="px-4 py-2 rounded-lg text-xs font-bold transition-all"
                style={{
                  background: 'rgba(0, 229, 204, 0.2)',
                  border: '1px solid var(--aimaru-cyan)',
                  color: 'var(--aimaru-cyan)'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(0, 229, 204, 0.3)'
                  e.currentTarget.style.boxShadow = '0 0 20px rgba(0, 229, 204, 0.5)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(0, 229, 204, 0.2)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                ✕ CLOSE
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}