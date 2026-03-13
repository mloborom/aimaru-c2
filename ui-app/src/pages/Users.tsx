import React, { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import type { User } from '../api'

export default function Users(){
  const { token, api } = useAuth()
  const [users, setUsers] = useState<User[]>([])
  const [newUser, setNewUser] = useState({ username:'', password:'', role:'viewer' as User['role'] })
  const [loading, setLoading] = useState(false)

  async function load(){ setLoading(true); try { const u = await api.listUsers(); setUsers(u||[]) } finally { setLoading(false) } }
  useEffect(()=>{ if (token) load() },[token])

  async function create(){ if (!newUser.username || !newUser.password) return; await api.createUser(newUser); setNewUser({ username:'', password:'', role:'viewer' }); await load() }
  async function toggle(id:string, disabled:boolean){ await api.updateUser(id, { disabled }); await load() }
  async function reset(id:string){ const p = prompt('New password:'); if (!p) return; await api.resetPassword(id, p); alert('Password updated') }
  async function remove(id:string){ if (!confirm('Delete user?')) return; await api.deleteUser(id); await load() }

  if (!token) return <div className="rounded-2xl p-4 glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-cyan)', color: 'var(--aimaru-cyan)'}}>Please log in.</div>

  return (
    <div className="space-y-4">
      <div className="rounded-2xl p-4 glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)'}}>
        <div className="font-semibold mb-2 glow-text-cyan" style={{color: 'var(--aimaru-cyan)'}}>Create User</div>
        <div className="grid sm:grid-cols-4 gap-2">
          <input className="rounded-xl px-3 py-2" placeholder="username" value={newUser.username} onChange={e=>setNewUser(s=>({...s, username:e.target.value}))} />
          <input className="rounded-xl px-3 py-2" placeholder="password" type="password" value={newUser.password} onChange={e=>setNewUser(s=>({...s, password:e.target.value}))} />
          <select className="rounded-xl px-3 py-2" value={newUser.role} onChange={e=>setNewUser(s=>({...s, role: e.target.value as User['role']}))}>
            <option value="admin">admin</option>
            <option value="operator">operator</option>
            <option value="viewer">viewer</option>
          </select>
          <button className="rounded-xl px-4 py-2 hover:glow-cyan-strong transition-all" style={{background: 'var(--aimaru-cyan)', color: 'var(--aimaru-dark-bg)', fontWeight: 'bold'}} onClick={create}>Create</button>
        </div>
      </div>

      <div className="rounded-2xl p-4 overflow-auto glow-cyan" style={{background: 'var(--aimaru-dark-card)', border: '1px solid var(--aimaru-dark-border)'}}>
        <div className="font-semibold mb-2 glow-text-cyan" style={{color: 'var(--aimaru-cyan)'}}>Users</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left" style={{borderBottom: '1px solid var(--aimaru-dark-border)'}}>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>ID</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Username</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Role</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Status</th>
              <th className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u=> (
              <tr key={u.id} style={{borderBottom: '1px solid var(--aimaru-dark-border)'}}>
                <td className="py-2 pr-2 font-mono text-xs" style={{color: 'var(--aimaru-text-dim)'}}>{u.id}</td>
                <td className="py-2 pr-2" style={{color: 'var(--aimaru-text)'}}>{u.username}</td>
                <td className="py-2 pr-2" style={{color: 'var(--aimaru-text-dim)'}}>{u.role}</td>
                <td className="py-2 pr-2" style={{color: 'var(--aimaru-text-dim)'}}>{u.disabled? 'disabled':'active'}</td>
                <td className="py-2 pr-2 flex gap-2">
                  <button className="rounded-lg px-3 py-1 hover:opacity-80" style={{background: 'var(--aimaru-gray)', color: 'var(--aimaru-text)'}} onClick={()=>toggle(u.id, !u.disabled)}>{u.disabled? 'Enable':'Disable'}</button>
                  <button className="rounded-lg px-3 py-1 hover:opacity-80" style={{background: 'var(--aimaru-gray)', color: 'var(--aimaru-text)'}} onClick={()=>reset(u.id)}>Reset PW</button>
                  <button className="rounded-lg px-3 py-1 hover:opacity-80" style={{background: 'rgba(239, 68, 68, 0.2)', border: '1px solid #EF4444', color: '#EF4444'}} onClick={()=>remove(u.id)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="text-sm mt-2" style={{color: 'var(--aimaru-text-dim)'}}>Loading…</div>}
      </div>
    </div>
  )
}