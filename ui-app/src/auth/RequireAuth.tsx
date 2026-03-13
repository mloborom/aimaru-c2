import React from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext'

export function RequireAuth({ children, roles }: { children: React.ReactNode; roles?: ("admin"|"operator"|"viewer")[] }){
  const { token, user } = useAuth()
  if (!token) return <Navigate to="/login" replace />
  if (roles && user && !roles.includes(user.role)) return <Navigate to="/" replace />
  return <>{children}</>
}