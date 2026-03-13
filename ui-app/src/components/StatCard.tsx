export function StatCard({ label, value }:{ label:string; value:number|string }){
  return (
    <div className="bg-white rounded-2xl shadow p-4">
      <div className="text-slate-500 text-sm">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  )
}