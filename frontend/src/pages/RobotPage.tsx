import { useEffect, useState } from 'react'
import { Bot, Play, Square, Settings2, TrendingUp, TrendingDown, Minus, Volume2, VolumeX } from 'lucide-react'
import { clsx } from 'clsx'
import { useAppSelector } from '../store/hooks'
import { api } from '../services/api'
import { setRobotConfig } from '../store/slices/robotSlice'
import { useAppDispatch } from '../store/hooks'
import { setSoundEnabled } from '../services/websocket'
import type { RobotConfig } from '../store/slices/robotSlice'

function tradeStatusColor(status: string | undefined): string {
  if (status === 'CLOSED_SL') return 'text-red-400 bg-red-500/10'
  if (status?.includes('T3') || status?.includes('T2')) return 'text-green-400 bg-green-500/10'
  if (status?.includes('T1')) return 'text-yellow-400 bg-yellow-500/10'
  return 'text-[#8b949e] bg-[#8b949e]/10'
}

export default function RobotPage() {
  const dispatch = useAppDispatch()
  const { running, config, activeTrades, tradeHistory, todayPnl, todayTrades, analysis } = useAppSelector(s => s.robot)
  const [configOpen, setConfigOpen] = useState(false)
  const [draft, setDraft] = useState<Partial<RobotConfig>>({})
  const [saving, setSaving] = useState(false)
  const [soundOn, setSoundOn] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)

  // Load config on mount
  useEffect(() => {
    api.getRobotConfig().then(cfg => {
      dispatch(setRobotConfig(cfg))
      setDraft(cfg)
    }).catch(() => {})
  }, [dispatch])

  // Sync draft when config updates externally
  useEffect(() => {
    if (config) setDraft({ ...config })
  }, [config])

  const handleStart = async () => {
    setActionLoading(true)
    try { await api.startRobot() } catch { } finally { setActionLoading(false) }
  }

  const handleStop = async () => {
    setActionLoading(true)
    try { await api.stopRobot() } catch { } finally { setActionLoading(false) }
  }

  const handleSaveConfig = async () => {
    setSaving(true)
    try {
      const res = await api.updateRobotConfig(draft)
      dispatch(setRobotConfig(res.config))
    } catch { } finally { setSaving(false) }
  }

  const toggleSound = () => {
    const next = !soundOn
    setSoundOn(next)
    setSoundEnabled(next)
  }

  const set = (key: keyof RobotConfig, val: any) => setDraft(d => ({ ...d, [key]: val }))

  return (
    <div className="flex flex-col h-full overflow-auto bg-[#0d1117]">
      {/* Status Header */}
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 bg-[#161b22] border-b border-[#30363d] shrink-0">
        <div className={clsx('w-2.5 h-2.5 rounded-full shrink-0', running ? 'bg-green-400 animate-pulse' : 'bg-red-400')} />
        <Bot size={16} className={running ? 'text-green-400' : 'text-[#8b949e]'} />
        <span className="text-sm font-semibold text-white">{running ? 'Robot Running' : 'Robot Stopped'}</span>

        <button
          onClick={running ? handleStop : handleStart}
          disabled={actionLoading}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold transition-colors',
            running
              ? 'bg-red-500 hover:bg-red-400 text-white'
              : 'bg-green-500 hover:bg-green-400 text-white',
            actionLoading && 'opacity-50 cursor-not-allowed'
          )}
        >
          {running ? <Square size={12} /> : <Play size={12} />}
          {running ? 'Stop Robot' : 'Start Robot'}
        </button>

        <button
          onClick={() => setConfigOpen(v => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-[#8b949e] hover:text-white hover:bg-[#1c2128] transition-colors"
        >
          <Settings2 size={12} />
          Config
        </button>

        <div className="ml-auto flex items-center gap-4 text-xs">
          <Stat label="Today Trades" value={String(todayTrades)} />
          <Stat
            label="Today P&L"
            value={`₹${todayPnl.toFixed(0)}`}
            color={todayPnl >= 0 ? 'text-green-400' : 'text-red-400'}
          />
          <Stat label="Open" value={String(activeTrades.length)} color="text-blue-400" />
          <button onClick={toggleSound} className="text-[#8b949e] hover:text-white" title="Toggle sound">
            {soundOn ? <Volume2 size={14} /> : <VolumeX size={14} />}
          </button>
        </div>
      </div>

      {/* Config Panel */}
      {configOpen && (
        <div className="border-b border-[#30363d] bg-[#161b22] px-4 py-4">
          <h3 className="text-xs font-semibold text-white mb-3">Robot Configuration</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <ConfigField label="Strike Selection">
              <select value={draft.strike_selection ?? 'ATM'} onChange={e => set('strike_selection', e.target.value)}
                className="input-field w-full">
                {['ATM','OTM1','OTM2','ITM1'].map(v => <option key={v}>{v}</option>)}
              </select>
            </ConfigField>

            <ConfigField label="Expiry">
              <select value={draft.expiry_preference ?? 'WEEKLY'} onChange={e => set('expiry_preference', e.target.value)}
                className="input-field w-full">
                <option>WEEKLY</option><option>MONTHLY</option>
              </select>
            </ConfigField>

            <ConfigField label="Timeframe">
              <select value={draft.timeframe ?? '15m'} onChange={e => set('timeframe', e.target.value)}
                className="input-field w-full">
                <option value="5m">5m</option><option value="15m">15m</option>
              </select>
            </ConfigField>

            <ConfigField label="Max Lots / Trade">
              <input type="number" min={1} max={10} value={draft.max_lots_per_trade ?? 2}
                onChange={e => set('max_lots_per_trade', +e.target.value)}
                className="input-field w-full" />
            </ConfigField>

            <ConfigField label="Capital / Trade %">
              <input type="number" min={1} max={20} step={0.5} value={draft.capital_per_trade_pct ?? 5}
                onChange={e => set('capital_per_trade_pct', +e.target.value)}
                className="input-field w-full" />
            </ConfigField>

            <ConfigField label="Stop Loss %">
              <input type="number" min={5} max={80} value={draft.stoploss_pct ?? 30}
                onChange={e => set('stoploss_pct', +e.target.value)}
                className="input-field w-full" />
            </ConfigField>

            <ConfigField label="Target 1 %">
              <input type="number" min={10} max={200} value={draft.target1_pct ?? 30}
                onChange={e => set('target1_pct', +e.target.value)}
                className="input-field w-full" />
            </ConfigField>

            <ConfigField label="Target 2 %">
              <input type="number" min={20} max={400} value={draft.target2_pct ?? 60}
                onChange={e => set('target2_pct', +e.target.value)}
                className="input-field w-full" />
            </ConfigField>

            <ConfigField label="Target 3 %">
              <input type="number" min={30} max={500} value={draft.target3_pct ?? 100}
                onChange={e => set('target3_pct', +e.target.value)}
                className="input-field w-full" />
            </ConfigField>

            <ConfigField label="Max Trades / Day">
              <input type="number" min={1} max={10} value={draft.max_trades_per_day ?? 3}
                onChange={e => set('max_trades_per_day', +e.target.value)}
                className="input-field w-full" />
            </ConfigField>

            <ConfigField label="Auto Sq-Off Time">
              <input type="time" value={draft.auto_square_off_time ?? '15:15'}
                onChange={e => set('auto_square_off_time', e.target.value)}
                className="input-field w-full" />
            </ConfigField>

            <ConfigField label="Trail SL after T1">
              <label className="flex items-center gap-2 mt-1 cursor-pointer">
                <input type="checkbox" checked={draft.trail_sl_after_t1 ?? true}
                  onChange={e => set('trail_sl_after_t1', e.target.checked)}
                  className="w-4 h-4 accent-blue-500" />
                <span className="text-xs text-[#8b949e]">Enabled</span>
              </label>
            </ConfigField>
          </div>

          <div className="flex items-center gap-2 mt-4">
            <button onClick={handleSaveConfig} disabled={saving}
              className="px-4 py-1.5 bg-blue-500 hover:bg-blue-400 text-white text-xs font-semibold rounded transition-colors disabled:opacity-50">
              {saving ? 'Saving…' : 'Save Config'}
            </button>
            <button onClick={() => setConfigOpen(false)} className="px-4 py-1.5 text-xs text-[#8b949e] hover:text-white">
              Close
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-4 p-4 flex-1">
        {/* Live Analysis */}
        <section>
          <h2 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">Live Analysis</h2>
          {Object.keys(analysis).length === 0 ? (
            <p className="text-xs text-[#8b949e]">
              {running ? 'Waiting for first analysis cycle (5 min)…' : 'Start the robot to see live analysis.'}
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {Object.values(analysis).map(a => (
                <div key={a.symbol} className="bg-[#161b22] border border-[#30363d] rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-bold text-white">{a.symbol}</span>
                    <div className="flex items-center gap-2">
                      {a.trend === 'UPTREND' ? <TrendingUp size={13} className="text-green-400" />
                        : a.trend === 'DOWNTREND' ? <TrendingDown size={13} className="text-red-400" />
                          : <Minus size={13} className="text-yellow-400" />}
                      <span className="text-xs text-[#8b949e]">{a.trend}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={clsx('text-xs font-bold px-2 py-0.5 rounded',
                      a.signal_type === 'BUY' ? 'bg-green-500/20 text-green-400'
                        : a.signal_type === 'SELL' ? 'bg-red-500/20 text-red-400'
                          : 'bg-yellow-500/20 text-yellow-400'
                    )}>{a.signal_type}</span>
                    {a.signal_strength !== undefined && (
                      <span className="text-xs text-[#8b949e]">{(a.signal_strength * 100).toFixed(0)}% confidence</span>
                    )}
                    {a.underlying_price && (
                      <span className="text-xs font-mono text-white ml-auto">₹{a.underlying_price.toLocaleString()}</span>
                    )}
                  </div>
                  {a.reasons && a.reasons.length > 0 && (
                    <ul className="space-y-0.5">
                      {a.reasons.slice(0, 3).map((r, i) => (
                        <li key={i} className="text-[10px] text-[#8b949e] flex items-start gap-1">
                          <span className="text-green-400 shrink-0">›</span>{r}
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="text-[10px] text-[#8b949e]/60 mt-1">
                    {a.timestamp ? new Date(a.timestamp).toLocaleTimeString('en-IN') : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Active Trades */}
        {activeTrades.length > 0 && (
          <section>
            <h2 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">Active Trades</h2>
            <div className="bg-[#161b22] border border-[#30363d] rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead className="border-b border-[#30363d]">
                  <tr className="text-[#8b949e]">
                    {['Symbol','Option','Strike','Expiry','Entry','Current','SL','T1','T2','Lots','P&L','Status'].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-medium text-[10px] tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {activeTrades.map(t => (
                    <tr key={t.id} className="border-b border-[#30363d]/40 hover:bg-[#1c2128]/50">
                      <td className="px-3 py-2 font-semibold text-white">{t.symbol}</td>
                      <td className={clsx('px-3 py-2 font-bold', t.option_type === 'CE' ? 'text-green-400' : 'text-red-400')}>{t.option_type}</td>
                      <td className="px-3 py-2 font-mono text-white">{t.strike}</td>
                      <td className="px-3 py-2 text-[#8b949e]">{t.expiry}</td>
                      <td className="px-3 py-2 font-mono text-[#8b949e]">₹{t.entry_price.toFixed(2)}</td>
                      <td className="px-3 py-2 font-mono text-white">₹{t.current_price.toFixed(2)}</td>
                      <td className="px-3 py-2 font-mono text-red-400">₹{t.sl_price.toFixed(2)}</td>
                      <td className="px-3 py-2 font-mono text-yellow-400">
                        ₹{t.t1_price.toFixed(2)}
                        {t.t1_hit && <span className="ml-1 text-[9px] text-green-400">✓</span>}
                      </td>
                      <td className="px-3 py-2 font-mono text-blue-400">₹{t.t2_price.toFixed(2)}</td>
                      <td className="px-3 py-2 text-[#8b949e]">{t.lots}</td>
                      <td className={clsx('px-3 py-2 font-mono font-semibold', t.pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                        {t.pnl >= 0 ? '+' : ''}₹{t.pnl.toFixed(0)}
                        <span className="text-[10px] ml-1 opacity-70">({t.pnl_pct.toFixed(1)}%)</span>
                      </td>
                      <td className="px-3 py-2">
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-blue-500/20 text-blue-400">OPEN</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Trade History */}
        {tradeHistory.length > 0 && (
          <section>
            <h2 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-2">Trade History</h2>
            <div className="bg-[#161b22] border border-[#30363d] rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead className="border-b border-[#30363d]">
                  <tr className="text-[#8b949e]">
                    {['Time','Symbol','Option','Strike','Entry','Exit','Lots','P&L','Status'].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-medium text-[10px] tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tradeHistory.slice(0, 30).map(t => {
                    return (
                      <tr key={t.id} className="border-b border-[#30363d]/40 hover:bg-[#1c2128]/50">
                        <td className="px-3 py-1.5 text-[#8b949e]">
                          {t.entry_time ? new Date(t.entry_time).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '—'}
                        </td>
                        <td className="px-3 py-1.5 font-semibold text-white">{t.symbol}</td>
                        <td className={clsx('px-3 py-1.5 font-bold', t.option_type === 'CE' ? 'text-green-400' : 'text-red-400')}>{t.option_type}</td>
                        <td className="px-3 py-1.5 font-mono text-white">{t.strike}</td>
                        <td className="px-3 py-1.5 font-mono text-[#8b949e]">₹{t.entry_price.toFixed(2)}</td>
                        <td className="px-3 py-1.5 font-mono text-[#8b949e]">{t.exit_price ? `₹${t.exit_price.toFixed(2)}` : '—'}</td>
                        <td className="px-3 py-1.5 text-[#8b949e]">{t.lots}</td>
                        <td className={clsx('px-3 py-1.5 font-mono font-semibold', t.pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                          {t.pnl >= 0 ? '+' : ''}₹{t.pnl.toFixed(0)}
                        </td>
                        <td className="px-3 py-1.5">
                          <span className={clsx('px-1.5 py-0.5 rounded text-[10px] font-medium', tradeStatusColor(t.status))}>
                            {t.status?.replace('CLOSED_', '') ?? '—'}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {activeTrades.length === 0 && tradeHistory.length === 0 && !running && (
          <div className="flex-1 flex items-center justify-center text-center py-16">
            <div>
              <Bot size={40} className="text-[#30363d] mx-auto mb-3" />
              <p className="text-sm text-[#8b949e]">Robot is idle. Configure and start it to begin paper trading.</p>
              <p className="text-xs text-[#8b949e]/60 mt-1">NIFTY & BANKNIFTY options · SMC + price action strategy</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, color = 'text-white' }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[#8b949e]">{label}:</span>
      <span className={clsx('font-mono font-semibold', color)}>{value}</span>
    </div>
  )
}

function ConfigField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] text-[#8b949e] mb-1 uppercase tracking-wide">{label}</label>
      {children}
    </div>
  )
}
