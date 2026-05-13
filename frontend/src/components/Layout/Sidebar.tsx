import { useState } from 'react'
import { Search, TrendingUp, TrendingDown } from 'lucide-react'
import { useAppSelector, useAppDispatch } from '../../store/hooks'
import { setSymbol } from '../../store/slices/chartSlice'
import { clsx } from 'clsx'
import { api } from '../../services/api'

const DEFAULT_WATCHLIST = [
  { symbol: 'NIFTY',     exchange: 'NSE', name: 'Nifty 50',      token: '26000', segment: 'IDX' },
  { symbol: 'BANKNIFTY', exchange: 'NSE', name: 'Bank Nifty',    token: '26009', segment: 'IDX' },
  { symbol: 'FINNIFTY',  exchange: 'NSE', name: 'Fin Nifty',     token: '26037', segment: 'IDX' },
  { symbol: 'RELIANCE',  exchange: 'NSE', name: 'Reliance',      token: '2885',  segment: 'EQ'  },
  { symbol: 'TCS',       exchange: 'NSE', name: 'TCS',           token: '11536', segment: 'EQ'  },
  { symbol: 'HDFCBANK',  exchange: 'NSE', name: 'HDFC Bank',     token: '1333',  segment: 'EQ'  },
  { symbol: 'INFY',      exchange: 'NSE', name: 'Infosys',       token: '1594',  segment: 'EQ'  },
  { symbol: 'ICICIBANK', exchange: 'NSE', name: 'ICICI Bank',    token: '4963',  segment: 'EQ'  },
  { symbol: 'SBIN',      exchange: 'NSE', name: 'SBI',           token: '3045',  segment: 'EQ'  },
  { symbol: 'ADANIENT',  exchange: 'NSE', name: 'Adani Ent.',    token: '25',    segment: 'EQ'  },
  { symbol: 'BAJFINANCE',exchange: 'NSE', name: 'Bajaj Finance', token: '317',   segment: 'EQ'  },
  { symbol: 'USDINR',    exchange: 'CDS', name: 'USD/INR Fut.',  token: '0',     segment: 'CUR' },
  { symbol: 'GOLDM',     exchange: 'MCX', name: 'Gold Mini',     token: '0',     segment: 'COM' },
  { symbol: 'CRUDEOIL',  exchange: 'MCX', name: 'Crude Oil',     token: '0',     segment: 'COM' },
]

export default function Sidebar() {
  const dispatch = useAppDispatch()
  const { activeSymbol } = useAppSelector(s => s.chart)
  const { quotes } = useAppSelector(s => s.market)
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])

  const handleSearch = async (q: string) => {
    setQuery(q)
    if (q.length < 1) { setSearchResults([]); return }
    try {
      const res = await api.searchSymbols(q)
      setSearchResults(res.results || [])
    } catch { setSearchResults([]) }
  }

  const selectSymbol = (item: any) => {
    dispatch(setSymbol({
      symbol: item.symbol,
      exchange: item.exchange,
      name: item.name || item.symbol,
      token: item.token,
      segment: item.segment,
    }))
    setQuery('')
    setSearchResults([])
  }

  const list = query ? searchResults : DEFAULT_WATCHLIST

  return (
    <aside className="w-56 flex flex-col bg-[#161b22] border-r border-[#30363d] shrink-0">
      {/* Search */}
      <div className="p-2 border-b border-[#30363d]">
        <div className="flex items-center gap-2 bg-[#0d1117] border border-[#30363d] rounded px-2 py-1.5">
          <Search size={12} className="text-[#8b949e]" />
          <input
            type="text"
            placeholder="Search symbol..."
            value={query}
            onChange={e => handleSearch(e.target.value)}
            className="bg-transparent text-xs text-white outline-none w-full placeholder-[#8b949e]"
          />
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {list.map((item) => {
          const quote = quotes[item.symbol]
          const isActive = activeSymbol.symbol === item.symbol
          const pct = quote?.change_pct ?? 0
          const positive = pct >= 0

          return (
            <button
              key={`${item.symbol}-${item.exchange}`}
              onClick={() => selectSymbol(item)}
              className={clsx(
                'w-full flex items-center justify-between px-3 py-2 text-left transition-colors border-b border-[#30363d]/50',
                isActive ? 'bg-blue-500/10 border-l-2 border-l-blue-500' : 'hover:bg-[#1c2128]'
              )}
            >
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-medium text-white truncate">{item.symbol}</span>
                <span className="text-[10px] text-[#8b949e] truncate">{item.name}</span>
              </div>
              <div className="flex flex-col items-end shrink-0 ml-1">
                {quote ? (
                  <>
                    <span className="text-xs font-mono text-white">{quote.ltp.toFixed(2)}</span>
                    <span className={clsx('text-[10px] font-mono flex items-center gap-0.5', positive ? 'text-green-400' : 'text-red-400')}>
                      {positive ? <TrendingUp size={9} /> : <TrendingDown size={9} />}
                      {positive ? '+' : ''}{pct.toFixed(2)}%
                    </span>
                  </>
                ) : (
                  <span className="text-[10px] text-[#8b949e]">–</span>
                )}
              </div>
            </button>
          )
        })}
      </div>
    </aside>
  )
}
