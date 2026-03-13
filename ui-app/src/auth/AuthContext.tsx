import React, { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { Api, LoginResponse, User } from '../api'

interface AuthCtx {
  token: string | null
  user: User | null
  api: Api
  login: (u: string, p: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }){
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('auth.token'))
  const [user, setUser] = useState<User | null>(() => {
    try { const raw = localStorage.getItem('auth.user'); return raw? JSON.parse(raw): null } catch { return null }
  })

  const api = useMemo(() => new Api({
    getToken: () => token,
    onUnauthorized: async () => {
      try {
        const j = await new Api({ getToken: ()=>token }).refresh().catch(()=>null)
        if (j && (j as LoginResponse).access_token) {
          setToken((j as LoginResponse).access_token)
          localStorage.setItem('auth.token', (j as LoginResponse).access_token)
        } else {
          logout()
        }
      } catch { logout() }
    },
  }), [token])

  const login = useCallback(async (username: string, password: string) => {
    const j = await api.login(username, password)
    setToken(j.access_token)
    localStorage.setItem('auth.token', j.access_token)
    if (j.user) { setUser(j.user); localStorage.setItem('auth.user', JSON.stringify(j.user)) }
  }, [api])

  const logout = useCallback(()=>{
    setToken(null); setUser(null)
    localStorage.removeItem('auth.token')
    localStorage.removeItem('auth.user')
  },[])

  const value = useMemo(()=>({ token, user, api, login, logout }), [token, user, api, login, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(){
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used within AuthProvider')
  return v
}