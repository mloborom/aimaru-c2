import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Nav(){
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const linkStyle = ({ isActive }: any) => ({
    className: `rounded-md px-4 py-2 text-sm font-bold uppercase tracking-wide transition-all ${isActive ? 'glow-text-cyan' : ''}`,
    style: {
      background: isActive ? 'rgba(0, 229, 204, 0.2)' : 'transparent',
      border: `1px solid ${isActive ? 'var(--aimaru-cyan)' : 'transparent'}`,
      color: isActive ? 'var(--aimaru-cyan)' : 'var(--aimaru-text-dim)',
      boxShadow: isActive ? '0 0 15px rgba(0, 229, 204, 0.3)' : 'none'
    }
  })

  return (
    <nav className="ml-auto flex items-center gap-3">
      <NavLink to="/" end {...linkStyle({ isActive: window.location.pathname === '/' })}
               onMouseEnter={(e) => {
                 if (window.location.pathname !== '/') {
                   e.currentTarget.style.background = 'rgba(0, 229, 204, 0.1)'
                   e.currentTarget.style.color = 'var(--aimaru-text)'
                 }
               }}
               onMouseLeave={(e) => {
                 if (window.location.pathname !== '/') {
                   e.currentTarget.style.background = 'transparent'
                   e.currentTarget.style.color = 'var(--aimaru-text-dim)'
                 }
               }}>
        Dashboard
      </NavLink>
      <NavLink to="/clients" {...linkStyle({ isActive: window.location.pathname === '/clients' })}
               onMouseEnter={(e) => {
                 if (window.location.pathname !== '/clients') {
                   e.currentTarget.style.background = 'rgba(0, 229, 204, 0.1)'
                   e.currentTarget.style.color = 'var(--aimaru-text)'
                 }
               }}
               onMouseLeave={(e) => {
                 if (window.location.pathname !== '/clients') {
                   e.currentTarget.style.background = 'transparent'
                   e.currentTarget.style.color = 'var(--aimaru-text-dim)'
                 }
               }}>
        Clients
      </NavLink>
      <NavLink to="/llm" {...linkStyle({ isActive: window.location.pathname === '/llm' })}
               onMouseEnter={(e) => {
                 if (window.location.pathname !== '/llm') {
                   e.currentTarget.style.background = 'rgba(0, 229, 204, 0.1)'
                   e.currentTarget.style.color = 'var(--aimaru-text)'
                 }
               }}
               onMouseLeave={(e) => {
                 if (window.location.pathname !== '/llm') {
                   e.currentTarget.style.background = 'transparent'
                   e.currentTarget.style.color = 'var(--aimaru-text-dim)'
                 }
               }}>
        LLM
      </NavLink>
      <NavLink to="/users" {...linkStyle({ isActive: window.location.pathname === '/users' })}
               onMouseEnter={(e) => {
                 if (window.location.pathname !== '/users') {
                   e.currentTarget.style.background = 'rgba(0, 229, 204, 0.1)'
                   e.currentTarget.style.color = 'var(--aimaru-text)'
                 }
               }}
               onMouseLeave={(e) => {
                 if (window.location.pathname !== '/users') {
                   e.currentTarget.style.background = 'transparent'
                   e.currentTarget.style.color = 'var(--aimaru-text-dim)'
                 }
               }}>
        Users
      </NavLink>
      <NavLink to="/my-keys" {...linkStyle({ isActive: window.location.pathname === '/my-keys' })}
               onMouseEnter={(e) => {
                 if (window.location.pathname !== '/my-keys') {
                   e.currentTarget.style.background = 'rgba(0, 229, 204, 0.1)'
                   e.currentTarget.style.color = 'var(--aimaru-text)'
                 }
               }}
               onMouseLeave={(e) => {
                 if (window.location.pathname !== '/my-keys') {
                   e.currentTarget.style.background = 'transparent'
                   e.currentTarget.style.color = 'var(--aimaru-text-dim)'
                 }
               }}>
        My Keys
      </NavLink>
      <NavLink to="/amsi" {...linkStyle({ isActive: window.location.pathname === '/amsi' })}
               onMouseEnter={(e) => {
                 if (window.location.pathname !== '/amsi') {
                   e.currentTarget.style.background = 'rgba(220, 38, 38, 0.1)'
                   e.currentTarget.style.color = 'var(--aimaru-text)'
                 }
               }}
               onMouseLeave={(e) => {
                 if (window.location.pathname !== '/amsi') {
                   e.currentTarget.style.background = 'transparent'
                   e.currentTarget.style.color = 'var(--aimaru-text-dim)'
                 }
               }}
               style={{
                 ...linkStyle({ isActive: window.location.pathname === '/amsi' }).style,
                 ...(window.location.pathname === '/amsi' ? {
                   background: 'rgba(220, 38, 38, 0.2)',
                   borderColor: '#DC2626',
                   color: '#DC2626',
                   boxShadow: '0 0 15px rgba(220, 38, 38, 0.3)'
                 } : {})
               }}>
        🛡️ AMSI
      </NavLink>

      <div className="ml-3 px-3 py-1 rounded-md text-xs font-mono border"
           style={{
             background: 'rgba(0, 229, 204, 0.05)',
             borderColor: 'var(--aimaru-dark-border)',
             color: 'var(--aimaru-text)'
           }}>
        {user ? `${user.username} [${user.role.toUpperCase()}]` : 'GUEST'}
      </div>

      {user ? (
        <button
          className="rounded-md px-4 py-2 text-sm font-bold uppercase tracking-wide transition-all"
          onClick={() => { logout(); navigate('/login'); }}
          style={{
            background: 'rgba(239, 68, 68, 0.2)',
            border: '1px solid #EF4444',
            color: '#EF4444'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(239, 68, 68, 0.3)'
            e.currentTarget.style.boxShadow = '0 0 15px rgba(239, 68, 68, 0.5)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'
            e.currentTarget.style.boxShadow = 'none'
          }}>
          Logout
        </button>
      ) : (
        <NavLink to="/login" {...linkStyle({ isActive: window.location.pathname === '/login' })}
                 onMouseEnter={(e) => {
                   if (window.location.pathname !== '/login') {
                     e.currentTarget.style.background = 'rgba(0, 229, 204, 0.1)'
                     e.currentTarget.style.color = 'var(--aimaru-text)'
                   }
                 }}
                 onMouseLeave={(e) => {
                   if (window.location.pathname !== '/login') {
                     e.currentTarget.style.background = 'transparent'
                     e.currentTarget.style.color = 'var(--aimaru-text-dim)'
                   }
                 }}>
          Login
        </NavLink>
      )}
    </nav>
  )
}