import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function Login(){
  const { login } = useAuth()
  const nav = useNavigate()
  const loc = useLocation() as any
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')

  async function onSubmit(e: React.FormEvent){
    e.preventDefault()
    setErr('')
    try {
      await login(username, password)
      const to = (loc.state && loc.state.from) || '/'
      nav(to, { replace: true })
    } catch (e:any) { setErr(e.message || 'Login failed') }
  }

  return (
    <div className="max-w-md mx-auto bg-white rounded-2xl shadow p-6">
      <h2 className="text-xl font-semibold mb-3">Sign in</h2>
      {err && <div className="mb-2 text-rose-600 text-sm">{err}</div>}
      <form className="space-y-3" onSubmit={onSubmit}>
        <input className="w-full rounded-xl border px-3 py-2" placeholder="Username" value={username} onChange={e=>setUsername(e.target.value)} />
        <input className="w-full rounded-xl border px-3 py-2" placeholder="Password" type="password" value={password} onChange={e=>setPassword(e.target.value)} />
        <button className="w-full rounded-xl bg-blue-600 text-white px-4 py-2">Login</button>
      </form>
    </div>
  )
}