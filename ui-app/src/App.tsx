import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import Dashboard from './pages/Dashboard'
import Clients from './pages/Clients'
import ClientDetail from './pages/ClientDetail'
import LLM from './pages/LLM'
import Login from './pages/Login'
import Users from './pages/Users'
import MyKeys from './pages/MyKeys'
import AMSIDeployment from './components/AMSIDeployment'
import { RequireAuth } from './auth/RequireAuth'

export default function App(){
  return (
    <Layout>
      <Routes>
        <Route path="/login" element={<Login/>} />

        <Route path="/" element={<RequireAuth><Dashboard/></RequireAuth>} />
        <Route path="/clients" element={<RequireAuth><Clients/></RequireAuth>} />
        <Route path="/clients/:id" element={<RequireAuth><ClientDetail/></RequireAuth>} />
        <Route path="/llm" element={<RequireAuth roles={["admin","operator"]}><LLM/></RequireAuth>} />
        <Route path="/users" element={<RequireAuth roles={["admin"]}><Users/></RequireAuth>} />
        <Route path="/my-keys" element={<RequireAuth><MyKeys/></RequireAuth>} />
        <Route path="/amsi" element={<RequireAuth roles={["admin","operator"]}><AMSIDeployment/></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}