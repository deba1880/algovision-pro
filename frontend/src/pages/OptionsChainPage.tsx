import { useEffect, useState, useMemo } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../services/api'
import { clsx } from 'clsx'

const INDICES = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']

interface OptionRow {
  strike: number
  expiry: string
  CE: { ltp: number; oi: number; oi_change: number; iv: number; volume: number; delta: number }
  PE: { ltp: number; oi: number; oi_change: number; iv: number; volume: number; delta: number }
}

export default function OptionsChainPage() {
  const [symbol, setSymbol] = useState('NIFTY')
  const [data, setData] = useState<any>(null)
  const [expiry, setExpiry] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchChain = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.getOptionsChain(symbol)
      setData(res)
      if (res.expiry_dates?.length && !expiry) setExpiry(res.expiry_dates[0])
    } catch (e: any) {
      if (e?.response?.status === 503) {
        setError('Options chain requires Indian network access. NSE India blocks requests from non-Indian IPs. This feature works when the backend is hosted in India.')
      } else {
        setError(e?.response?.data?.detail || e?.message || 'Failed to load options chain')
      }
    } finally { setLoading(false) }
  }

  useEffect(() => { fetchChain() }, [symbol])

  const rows: OptionRow[] = (data?.data || []).filter((r: any) => !expiry || r.expiry === expiry)
  const underlying = data?.underlying || 0
  const maxPain = data?.max_pain || 0
  const pcr = data?.pcr || 0

  const maxCeOi = useMemo(() => Math.max(...rows.map(r => r.CE?.oi || 0), 1), [rows])
  const maxPeOi = useMemo(() => Math.max(...rows.map(r => r.PE?.oi || 0), 1), [rows])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-[#161b22] border-b border-[#30363d]">
        {/* Symbol tabs */}
        <div className="flex gap-1">
          {INDICES.map(s => (
            <button key={s} onClick={() => setSymbol(s)}
              className={clsx('px-3 py-1 rounded text-xs font-medium transition-colors',
                symbol === s ? 'bg-blue-500 text-white' : 'text-[#8b949e] hover:bg-[#1c2128]'
              )}>
              {s}
            </button>
          ))}
        </div>

        {/* Expiry selector */}
        {data?.expiry_dates && (
          <select
            value={expiry}
            onChange={e => setExpiry(e.target.value)}
            className="bg-[#1c2128] border border-[#30363d] text-xs text-white rounded px-2 py-1"
          >
            {data.expiry_dates.map((e: string) => (
              <option key={e} value={e}>{e}</option>
            ))}
          </select>
        )}

        {/* Stats */}
        <div className="flex flex-wrap items-center gap-3 ml-auto text-xs">
          <Stat label="Spot" value={underlying.toFixed(2)} />
          <Stat label="Max Pain" value={maxPain.toFixed(0)} color="text-yellow-400" />
          <Stat label="PCR" value={pcr.toFixed(3)} color={pcr < 0.9 ? 'text-green-400' : pcr > 1.2 ? 'text-red-400' : 'text-white'} />
          <Stat label="CE OI" value={fmtOI(data?.total_ce_oi || 0)} color="text-green-400" />
          <Stat label="PE OI" value={fmtOI(data?.total_pe_oi || 0)} color="text-red-400" />
        </div>

        <button onClick={fetchChain} className="text-[#8b949e] hover:text-white ml-2">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Error / empty state */}
      {error && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center p-8 max-w-sm">
            <div className="text-3xl mb-3">🌐</div>
            <p className="text-sm font-semibold text-red-400 mb-2">Data Unavailable</p>
            <p className="text-xs text-[#8b949e]">{error}</p>
          </div>
        </div>
      )}

      {/* Table */}
      {!error && <div className="flex-1 overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[#161b22] border-b border-[#30363d] z-10">
            <tr>
              {['OI','OI Chg','Vol','IV','LTP','Delta','CALLS','','STRIKE','','PUTS','Delta','LTP','IV','Vol','OI Chg','OI'].map((h, i) => (
                <th key={i} className={clsx(
                  'px-2 py-2 text-[10px] font-medium tracking-wider',
                  h === 'CALLS' ? 'text-green-400' : h === 'PUTS' ? 'text-red-400' : h === 'STRIKE' ? 'text-yellow-400 text-center' : 'text-[#8b949e]',
                  i < 6 ? 'text-right' : i > 10 ? 'text-left' : 'text-center'
                )}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isATM = Math.abs(row.strike - underlying) < underlying * 0.005
              const isMaxPain = Math.abs(row.strike - maxPain) < 1
              return (
                <tr key={row.strike} className={clsx(
                  'border-b border-[#30363d]/40 hover:bg-[#1c2128]/50',
                  isATM && 'bg-blue-500/5 border-blue-500/20',
                  isMaxPain && 'bg-yellow-500/5',
                )}>
                  {/* CE side */}
                  <td className="px-2 py-1.5 text-right text-[#8b949e]">{fmtOI(row.CE?.oi)}</td>
                  <td className={clsx('px-2 py-1.5 text-right', row.CE?.oi_change > 0 ? 'text-green-400' : 'text-red-400')}>
                    {row.CE?.oi_change > 0 ? '+' : ''}{fmtOI(row.CE?.oi_change)}
                  </td>
                  <td className="px-2 py-1.5 text-right text-[#8b949e]">{fmtOI(row.CE?.volume)}</td>
                  <td className="px-2 py-1.5 text-right text-[#8b949e]">{row.CE?.iv?.toFixed(1)}%</td>
                  <td className="px-2 py-1.5 text-right text-green-400 font-mono font-semibold">{row.CE?.ltp?.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-right text-[#8b949e]">{row.CE?.delta?.toFixed(3)}</td>

                  {/* OI bar — CE */}
                  <td className="px-1 w-24">
                    <div className="flex justify-end">
                      <div className="h-1.5 rounded-sm bg-green-500/60" style={{ width: `${(row.CE?.oi / maxCeOi) * 80}px` }} />
                    </div>
                  </td>

                  {/* Strike */}
                  <td className={clsx('px-3 py-1.5 text-center font-mono font-bold',
                    isATM ? 'text-yellow-400' : 'text-white'
                  )}>
                    {row.strike}
                    {isATM && <span className="text-[9px] text-yellow-400 ml-1">ATM</span>}
                    {isMaxPain && <span className="text-[9px] text-orange-400 ml-1">MP</span>}
                  </td>

                  {/* OI bar — PE */}
                  <td className="px-1 w-24">
                    <div className="flex">
                      <div className="h-1.5 rounded-sm bg-red-500/60" style={{ width: `${(row.PE?.oi / maxPeOi) * 80}px` }} />
                    </div>
                  </td>

                  {/* PE side */}
                  <td className="px-2 py-1.5 text-left text-[#8b949e]">{row.PE?.delta?.toFixed(3)}</td>
                  <td className="px-2 py-1.5 text-left text-red-400 font-mono font-semibold">{row.PE?.ltp?.toFixed(2)}</td>
                  <td className="px-2 py-1.5 text-left text-[#8b949e]">{row.PE?.iv?.toFixed(1)}%</td>
                  <td className="px-2 py-1.5 text-left text-[#8b949e]">{fmtOI(row.PE?.volume)}</td>
                  <td className={clsx('px-2 py-1.5 text-left', row.PE?.oi_change > 0 ? 'text-green-400' : 'text-red-400')}>
                    {row.PE?.oi_change > 0 ? '+' : ''}{fmtOI(row.PE?.oi_change)}
                  </td>
                  <td className="px-2 py-1.5 text-left text-[#8b949e]">{fmtOI(row.PE?.oi)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>}
    </div>
  )
}

function Stat({ label, value, color = 'text-white' }: any) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[#8b949e]">{label}:</span>
      <span className={clsx('font-mono font-semibold', color)}>{value}</span>
    </div>
  )
}

function fmtOI(v: number): string {
  if (!v) return '–'
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(1)}K`
  return String(v)
}
