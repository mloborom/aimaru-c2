import React from 'react'

export function ClientList({ clients, onSelect, selected }:{ clients:{id:string, connected?:boolean}[]; onSelect:(id:string)=>void; selected?:string|null }){
  return (
    <div className="max-h-96 overflow-auto rounded-xl border">
      {clients.length===0 && <div className="p-3 text-sm text-slate-500">No clients found.</div>}
      {clients.map(c=> (
        <button key={c.id} onClick={()=>onSelect(c.id)} className={`w-full flex items-center justify-between px-3 py-2 border-b last:border-b-0 hover:bg-slate-50 ${selected===c.id?'bg-slate-100':''}`}>
          <span className="font-medium">{c.id}</span>
          <span className={`text-xs ${c.connected? 'text-emerald-600':'text-slate-400'}`}>{c.connected? 'connected':'unknown'}</span>
        </button>
      ))}
    </div>
  )
}