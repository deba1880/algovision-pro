import { useState, useEffect } from 'react'
import { api } from '../services/api'
import { clsx } from 'clsx'
import { PlayCircle } from 'lucide-react'

const SYMBOLS    = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN']
const TIMEFRAMES = ['5m', '15m', '30m', '1h', '1d']
const SEGMENTS   = [
  { value: 'SPOT',        label: 'Spot (Index/Equity)' },
  { value: 'FUTURES',     label: 'Futures (F&O)' },
  { value: 'OPTIONS_CE',  label: 'Options – ATM Call (CE)' },
  { value: 'OPTIONS_PE',  label: 'Options – ATM Put (PE)' },
]

const INTRADAY_60 = new Set(['5m', '15m', '30m'])

function daysAgo(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

function maxFromDate(tf: string) {
  if (INTRADAY_60.has(tf))  return daysAgo(59)
  if (tf === '1h')          return daysAgo(180)
  return daysAgo(180)
}

interface Metrics {
  total_trades: number
  total_return_pct?: number
  net_pnl?: number
  win_rate?: number
  profit_factor?: number
  sharpe_ratio?: number
  max_drawdown_pct?: number
  avg_rr?: number
  avg_win?: number
  avg_loss?: number
  initial_capital?: number
  note?: string
}

interface BacktestResult {
  metrics: Metrics
  equity_curve: [string, number][]
  segment: string
  lot_size: number
  trades: {
    entry_time: string
    exit_time?: string
    signal: 'BUY' | 'SELL'
    entry: number
    exit?: number
    sl: number
    tp: number
    qty: number
    pnl: number
    outcome: 'WIN' | 'LOSS' | 'OPEN'
  }[]
  data_range: { from: string; to: string; bars: number }
}

export default function BacktestPage() {
  const [config, setConfig] = useState({
    symbol: 'NIFTY',
    timeframe: '1d',
    from_date: daysAgo(180),
    to_date: daysAgo(0),
    initial_capital: 100000,
    risk_per_trade_pct: 1,
    sl_atr_mult: 1.5,
    tp_rr: 2.0,
    segment: 'SPOT',
    assumed_iv_pct: 15,
    option_dte: 15,
  })
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Auto-adjust from_date when timeframe changes to respect yfinance limits
  useEffect(() => {
    const limit = maxFromDate(config.timeframe)
    if (config.from_date < limit) {
      setConfig(p => ({ ...p, from_date: limit }))
    }
  }, [config.timeframe])

  const run = async () => {
    setLoading(true)
    setError('')
    try {
      setResult(await api.runBacktest(config))
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Backtest failed. Check symbol/date range.')
    } finally {
      setLoading(false)
    }
  }

  const set = (k: string, v: any) => setConfig(p => ({ ...p, [k]: v }))
  const isOptions = config.segment.startsWith('OPTIONS')

  return (
    <div className="p-4 grid grid-cols-1 md:grid-cols-4 gap-4 h-full overflow-auto">
      {/* ── Config Panel ─────────────────────────────── */}
      <div className="col-span-1 panel p-4 flex flex-col gap-3 self-start">
        <h3 className="text-sm font-semibold text-white">Backtest Config</h3>

        <Field label="Symbol">
          <select value={config.symbol} onChange={e => set('symbol', e.target.value)} className="input-field">
            {SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </Field>

        <Field label="Segment">
          <select value={config.segment} onChange={e => set('segment', e.target.value)} className="input-field">
            {SEGMENTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </Field>

        <Field label="Timeframe">
          <select value={config.timeframe} onChange={e => set('timeframe', e.target.value)} className="input-field">
            {TIMEFRAMES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </Field>

        <Field label="From Date">
          <input type="date" value={config.from_date} onChange={e => set('from_date', e.target.value)}
            min={INTRADAY_60.has(config.timeframe) ? daysAgo(59) : daysAgo(720)}
            max={config.to_date}
            className="input-field" />
        </Field>

        <Field label="To Date">
          <input type="date" value={config.to_date} onChange={e => set('to_date', e.target.value)}
            min={config.from_date} max={daysAgo(0)} className="input-field" />
        </Field>

        <Field label="Capital (₹)">
          <input type="number" step={10000} min={10000} value={config.initial_capital}
            onChange={e => set('initial_capital', Number(e.target.value))} className="input-field" />
        </Field>

        <Field label="Risk / Trade (%)">
          <input type="number" step={0.1} min={0.1} max={5} value={config.risk_per_trade_pct}
            onChange={e => set('risk_per_trade_pct', Number(e.target.value))} className="input-field" />
        </Field>

        <Field label="SL ATR Multiplier">
          <input type="number" step={0.1} min={0.5} max={5} value={config.sl_atr_mult}
            onChange={e => set('sl_atr_mult', Number(e.target.value))} className="input-field" />
        </Field>

        <Field label="Take-Profit R:R">
          <input type="number" step={0.1} min={1} max={10} value={config.tp_rr}
            onChange={e => set('tp_rr', Number(e.target.value))} className="input-field" />
        </Field>

        {/* Options-specific fields */}
        {isOptions && (
          <>
            <div className="border-t border-[#30363d] pt-2">
              <p className="text-[10px] text-[#8b949e] mb-2 uppercase tracking-wider">Options Parameters</p>
            </div>
            <Field label="Assumed IV (%)">
              <input type="number" step={0.5} min={5} max={80} value={config.assumed_iv_pct}
                onChange={e => set('assumed_iv_pct', Number(e.target.value))} className="input-field" />
            </Field>
            <Field label="Option DTE (days)">
              <input type="number" step={1} min={1} max={90} value={config.option_dte}
                onChange={e => set('option_dte', Number(e.target.value))} className="input-field" />
            </Field>
          </>
        )}

        <button onClick={run} disabled={loading}
          className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white py-2 rounded font-semibold text-sm mt-1 transition-colors"
        >
          <PlayCircle size={14} />
          {loading ? 'Running…' : 'Run Backtest'}
        </button>

        {error && (
          <div className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 p-2 rounded leading-relaxed">
            {error}
          </div>
        )}

        <div className="text-[10px] text-[#8b949e] leading-relaxed space-y-1">
          {INTRADAY_60.has(config.timeframe) && (
            <p>⚠ Intraday ≤30m data limited to last 60 days (Yahoo Finance).</p>
          )}
          {isOptions && (
            <p>Options P&amp;L uses Black-Scholes ATM approximation with the IV you set.</p>
          )}
          {config.segment === 'FUTURES' && (
            <p>Futures uses lot-size sizing (NIFTY=25, BANKNIFTY=15 per lot).</p>
          )}
          {config.segment === 'OPTIONS_CE' && (
            <p>Only BUY (bullish) signals are traded — buying ATM calls.</p>
          )}
          {config.segment === 'OPTIONS_PE' && (
            <p>Only SELL (bearish) signals are traded — buying ATM puts.</p>
          )}
        </div>
      </div>

      {/* ── Results Panel ────────────────────────────── */}
      <div className="col-span-1 md:col-span-3 flex flex-col gap-4">
        {!result && !loading && (
          <div className="panel flex items-center justify-center py-24 text-center">
            <div>
              <div className="text-4xl mb-3">📊</div>
              <p className="text-sm text-[#8b949e]">Configure a backtest on the left and click Run.</p>
              <p className="text-[10px] text-[#8b949e] mt-1">Strategy: BOS + pullback (SMC) · ATR SL · Fixed R:R TP</p>
              <p className="text-[10px] text-[#8b949e] mt-0.5">Segments: Spot · Futures · ATM Options CE/PE</p>
            </div>
          </div>
        )}

        {loading && (
          <div className="panel flex items-center justify-center py-24">
            <p className="text-sm text-[#8b949e] animate-pulse">Fetching 6-month data and running strategy…</p>
          </div>
        )}

        {result && !loading && (
          <>
            <div className="flex flex-wrap items-center gap-3 text-[10px] text-[#8b949e]">
              <span>Data: {result.data_range.from.slice(0, 10)} → {result.data_range.to.slice(0, 10)} · {result.data_range.bars} bars</span>
              <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 font-medium">
                {SEGMENTS.find(s => s.value === result.segment)?.label ?? result.segment}
              </span>
              {result.lot_size > 1 && (
                <span className="text-[#8b949e]">Lot size: {result.lot_size}</span>
              )}
            </div>

            {'total_return_pct' in result.metrics ? (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <Metric label="Total Return"   value={`${result.metrics.total_return_pct! >= 0 ? '+' : ''}${result.metrics.total_return_pct}%`}
                  sub={`₹${fmtNum(result.metrics.net_pnl!)} net P&L`} good={result.metrics.total_return_pct! >= 0} />
                <Metric label="Win Rate"        value={`${result.metrics.win_rate}%`}
                  sub={`${result.metrics.total_trades} trades`} good={result.metrics.win_rate! >= 50} />
                <Metric label="Profit Factor"   value={String(result.metrics.profit_factor)}
                  sub={`Avg win ₹${fmtNum(result.metrics.avg_win!)}`} good={result.metrics.profit_factor! >= 1} />
                <Metric label="Max Drawdown"    value={`${result.metrics.max_drawdown_pct}%`}
                  sub="from peak equity" good={result.metrics.max_drawdown_pct! < 10} invert />
                <Metric label="Sharpe Ratio"    value={String(result.metrics.sharpe_ratio)}
                  sub="annualised" good={result.metrics.sharpe_ratio! >= 1} />
                <Metric label="Avg Risk:Reward" value={`1:${result.metrics.avg_rr}`}
                  sub={`Avg loss ₹${fmtNum(result.metrics.avg_loss!)}`} good={result.metrics.avg_rr! >= 1.5} />
              </div>
            ) : (
              <div className="panel p-4 text-sm text-[#8b949e]">
                {result.metrics.note || 'No completed trades in this period.'}
              </div>
            )}

            {result.equity_curve.length > 2 && (
              <div className="panel p-4">
                <h3 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-3">Equity Curve</h3>
                <EquityCurve data={result.equity_curve} initial={result.metrics.initial_capital ?? 100000} />
              </div>
            )}

            {result.trades.length > 0 && (
              <div className="panel p-4">
                <h3 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-3">
                  Trade Log — {result.trades.length} trades
                  {isOptionsSegment(result.segment) && <span className="ml-2 text-yellow-400">(premiums shown)</span>}
                </h3>
                <div className="overflow-auto max-h-72">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-[#161b22]">
                      <tr className="text-[#8b949e] border-b border-[#30363d]">
                        {['Entry', 'Exit', 'Side', 'Qty', isOptionsSegment(result.segment) ? 'Premium In' : 'Entry Px',
                          isOptionsSegment(result.segment) ? 'Premium Out' : 'Exit Px', 'P&L', 'Result'].map(h => (
                          <th key={h} className="text-left py-1.5 pr-3 font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.trades.map((t, i) => (
                        <tr key={i} className="border-b border-[#30363d]/40 hover:bg-white/[0.02]">
                          <td className="py-1.5 pr-3 font-mono text-[10px] text-[#8b949e]">{t.entry_time.slice(0, 16)}</td>
                          <td className="py-1.5 pr-3 font-mono text-[10px] text-[#8b949e]">{t.exit_time?.slice(0, 16) ?? '–'}</td>
                          <td className={clsx('py-1.5 pr-3 font-semibold', t.signal === 'BUY' ? 'text-green-400' : 'text-red-400')}>
                            {t.signal}
                          </td>
                          <td className="py-1.5 pr-3 text-[#8b949e]">{t.qty}</td>
                          <td className="py-1.5 pr-3 font-mono">{t.entry.toFixed(2)}</td>
                          <td className="py-1.5 pr-3 font-mono">{t.exit?.toFixed(2) ?? '–'}</td>
                          <td className={clsx('py-1.5 pr-3 font-mono font-semibold', t.pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                            {t.pnl >= 0 ? '+' : ''}₹{fmtNum(t.pnl)}
                          </td>
                          <td className={clsx('py-1.5 text-xs font-medium',
                            t.outcome === 'WIN'  ? 'text-green-400' :
                            t.outcome === 'LOSS' ? 'text-red-400'   : 'text-yellow-400'
                          )}>{t.outcome}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function isOptionsSegment(seg: string) {
  return seg?.startsWith('OPTIONS')
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] text-[#8b949e] mb-1 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  )
}

function Metric({ label, value, sub, good, invert }: {
  label: string; value: string; sub?: string; good: boolean; invert?: boolean
}) {
  const color = invert
    ? (good ? 'text-green-400' : 'text-yellow-400')
    : (good ? 'text-green-400' : 'text-red-400')
  return (
    <div className="panel p-3">
      <div className="text-[10px] text-[#8b949e] uppercase tracking-wider mb-1">{label}</div>
      <div className={clsx('text-xl font-bold font-mono', color)}>{value}</div>
      {sub && <div className="text-[10px] text-[#8b949e] mt-0.5">{sub}</div>}
    </div>
  )
}

function EquityCurve({ data, initial }: { data: [string, number][]; initial: number }) {
  const step  = Math.max(1, Math.ceil(data.length / 600))
  const pts   = data.filter((_, i) => i % step === 0)
  const vals  = pts.map(d => d[1])
  const minV  = Math.min(...vals, initial)
  const maxV  = Math.max(...vals, initial)
  const range = maxV - minV || 1
  const W = 800, H = 110

  const coords = vals.map((v, i) => [
    (i / Math.max(vals.length - 1, 1)) * W,
    H - ((v - minV) / range) * (H - 4),
  ])

  const line = coords.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const area = `${line} L${W},${H} L0,${H} Z`
  const positive = vals[vals.length - 1] >= initial
  const col = positive ? '#22c55e' : '#ef4444'
  const baseY = H - ((initial - minV) / range) * (H - 4)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none" style={{ height: 110 }}>
      <defs>
        <linearGradient id="eqG" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={col} stopOpacity="0.25" />
          <stop offset="100%" stopColor={col} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <line x1="0" y1={baseY} x2={W} y2={baseY} stroke="#30363d" strokeWidth="0.5" strokeDasharray="4 3" />
      <path d={area} fill="url(#eqG)" />
      <path d={line} fill="none" stroke={col} strokeWidth="1.5" />
    </svg>
  )
}

function fmtNum(n: number): string {
  return Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
}
