export function StatusBadge({ status }:{ status:string }){
  const color = status === 'completed' ? 'bg-emerald-100 text-emerald-700' : status === 'delivered' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-700'
  return <span className={`px-2 py-1 rounded-full text-xs ${color}`}>{status}</span>
}