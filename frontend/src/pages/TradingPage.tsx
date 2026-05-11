import { useEffect, useState } from 'react'
import { useAppSelector, useAppDispatch } from '../store/hooks'
import { setPositions, setOrders } from '../store/slices/tradingSlice'
import { api } from '../services/api'
import { clsx } from 'clsx'
import { ShieldAlert } from 'lucide-react'

const EXCHANGES = ['NSE', 'BSE', 'NFO', 'MCX', 'CDS'] as const
const ORDER_TYPES = ['MARKET', 'LIMIT', 'SL', 'SL-M'] as const
const PRODUCT_TYPES = ['MIS', 'CNC', 'NRML'] as const

export default function TradingPage() {
  const dispatch = useAppDispatch()
  const { positions, orders, isPaperMode, dailyPnl } = useAppSelector(s => s.trading)
  const [orderForm, setOrderForm] = useState({
    symbol: 'NIFTY', exchange: 'NSE', transaction: 'BUY',
    order_type: 'MARKET', product: 'MIS', quantity: 1, price: 0,
  })
  const [placing, setPlacing] = useState(false)
  const [msg, setMsg] = useState('')

  const refresh = async () => {
    const [pos, ord] = await Promise.all([api.getPositions(), api.getOrders()])
    dispatch(setPositions(pos.positions))
    dispatch(setOrders(ord.orders))
  }

  useEffect(() => { refresh() }, [])

  const placeOrder = async () => {
    setPlacing(true)
    setMsg('')
    try {
      const res = await api.placeOrder(orderForm)
      setMsg(`✓ Order placed: ${res.message || 'Success'}`)
      await refresh()
    } catch (e: any) {
      setMsg(`✗ ${e.response?.data?.detail || 'Order failed'}`)
    } finally { setPlacing(false) }
  }

  return (
    <div className="p-4 grid grid-cols-3 gap-4 h-full">
      {/* Order form */}
      <div className="col-span-1 flex flex-col gap-4">
        <div className="panel p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-white">Place Order</h3>
            {isPaperMode && (
              <span className="chip bg-yellow-500/20 text-yellow-400 text-[10px] px-2 py-0.5 rounded">
                PAPER MODE
              </span>
            )}
          </div>

          <div className="space-y-3">
            <Field label="Symbol">
              <input
                value={orderForm.symbol}
                onChange={e => setOrderForm(p => ({ ...p, symbol: e.target.value.toUpperCase() }))}
                className="input-field"
              />
            </Field>

            <Field label="Exchange">
              <select value={orderForm.exchange} onChange={e => setOrderForm(p => ({ ...p, exchange: e.target.value }))} className="input-field">
                {EXCHANGES.map(x => <option key={x}>{x}</option>)}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-2">
              <button onClick={() => setOrderForm(p => ({ ...p, transaction: 'BUY' }))}
                className={clsx('py-2 rounded text-xs font-bold transition-colors',
                  orderForm.transaction === 'BUY' ? 'bg-green-500 text-white' : 'bg-green-500/10 text-green-400'
                )}>BUY</button>
              <button onClick={() => setOrderForm(p => ({ ...p, transaction: 'SELL' }))}
                className={clsx('py-2 rounded text-xs font-bold transition-colors',
                  orderForm.transaction === 'SELL' ? 'bg-red-500 text-white' : 'bg-red-500/10 text-red-400'
                )}>SELL</button>
            </div>

            <Field label="Order Type">
              <select value={orderForm.order_type} onChange={e => setOrderForm(p => ({ ...p, order_type: e.target.value }))} className="input-field">
                {ORDER_TYPES.map(x => <option key={x}>{x}</option>)}
              </select>
            </Field>

            <Field label="Product">
              <select value={orderForm.product} onChange={e => setOrderForm(p => ({ ...p, product: e.target.value }))} className="input-field">
                {PRODUCT_TYPES.map(x => <option key={x}>{x}</option>)}
              </select>
            </Field>

            <Field label="Quantity">
              <input type="number" min={1} value={orderForm.quantity}
                onChange={e => setOrderForm(p => ({ ...p, quantity: Number(e.target.value) }))}
                className="input-field" />
            </Field>

            {orderForm.order_type !== 'MARKET' && (
              <Field label="Price">
                <input type="number" min={0} step={0.05} value={orderForm.price}
                  onChange={e => setOrderForm(p => ({ ...p, price: Number(e.target.value) }))}
                  className="input-field" />
              </Field>
            )}

            <button
              onClick={placeOrder}
              disabled={placing}
              className={clsx('w-full py-2.5 rounded font-bold text-sm transition-colors',
                orderForm.transaction === 'BUY'
                  ? 'bg-green-500 hover:bg-green-400 text-white'
                  : 'bg-red-500 hover:bg-red-400 text-white',
                placing && 'opacity-60 cursor-not-allowed'
              )}
            >
              {placing ? 'Placing...' : `${orderForm.transaction} ${orderForm.symbol}`}
            </button>

            {msg && (
              <div className={clsx('text-xs rounded p-2', msg.startsWith('✓') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400')}>
                {msg}
              </div>
            )}
          </div>
        </div>

        {/* Risk controls notice */}
        <div className="panel p-3 border-yellow-500/20 bg-yellow-500/5">
          <div className="flex items-center gap-1.5 mb-1.5">
            <ShieldAlert size={12} className="text-yellow-400" />
            <span className="text-xs font-semibold text-yellow-400">Risk Controls Active</span>
          </div>
          <p className="text-[10px] text-[#8b949e] leading-relaxed">
            Max daily loss: 2% · Max order: ₹50K · Max positions: 5
          </p>
          <p className="text-[10px] text-yellow-400 mt-1">
            Daily P&L: <span className={dailyPnl >= 0 ? 'text-green-400' : 'text-red-400'}>
              ₹{dailyPnl.toFixed(0)}
            </span>
          </p>
        </div>
      </div>

      {/* Positions + Orders */}
      <div className="col-span-2 flex flex-col gap-4 overflow-auto">
        <div className="panel p-4">
          <h3 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-3">Open Positions</h3>
          {positions.length === 0
            ? <p className="text-xs text-[#8b949e]">No open positions</p>
            : (
              <table className="w-full text-xs">
                <thead><tr className="text-[#8b949e] border-b border-[#30363d]">
                  {['Symbol','Qty','Avg Price','LTP','P&L','P&L %'].map(h => (
                    <th key={h} className="text-left py-1 pr-3 font-medium">{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {positions.map(pos => (
                    <tr key={pos.id} className="border-b border-[#30363d]/40">
                      <td className="py-1.5 pr-3 font-medium text-white">{pos.symbol}</td>
                      <td className="py-1.5 pr-3">{pos.quantity}</td>
                      <td className="py-1.5 pr-3 font-mono">{pos.avg_price.toFixed(2)}</td>
                      <td className="py-1.5 pr-3 font-mono">{pos.ltp.toFixed(2)}</td>
                      <td className={clsx('py-1.5 pr-3 font-mono font-semibold', pos.pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                        {pos.pnl >= 0 ? '+' : ''}₹{pos.pnl.toFixed(0)}
                      </td>
                      <td className={clsx('py-1.5 font-mono', pos.pnl_pct >= 0 ? 'text-green-400' : 'text-red-400')}>
                        {pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct.toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>

        <div className="panel p-4">
          <h3 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-3">Recent Orders</h3>
          {orders.length === 0
            ? <p className="text-xs text-[#8b949e]">No orders yet</p>
            : (
              <table className="w-full text-xs">
                <thead><tr className="text-[#8b949e] border-b border-[#30363d]">
                  {['Time','Symbol','Type','Side','Qty','Price','Status'].map(h => (
                    <th key={h} className="text-left py-1 pr-3 font-medium">{h}</th>
                  ))}
                </tr></thead>
                <tbody>
                  {orders.slice(0, 20).map(ord => (
                    <tr key={ord.id} className="border-b border-[#30363d]/40">
                      <td className="py-1.5 pr-3 text-[#8b949e]">{new Date(ord.placed_at).toLocaleTimeString()}</td>
                      <td className="py-1.5 pr-3 font-medium text-white">{ord.symbol}</td>
                      <td className="py-1.5 pr-3 text-[#8b949e]">{ord.order_type}</td>
                      <td className={clsx('py-1.5 pr-3 font-semibold', ord.transaction === 'BUY' ? 'text-green-400' : 'text-red-400')}>
                        {ord.transaction}
                      </td>
                      <td className="py-1.5 pr-3">{ord.quantity}</td>
                      <td className="py-1.5 pr-3 font-mono">{ord.price?.toFixed(2) || '–'}</td>
                      <td className={clsx('py-1.5',
                        ord.status === 'COMPLETE' ? 'text-green-400' :
                        ord.status === 'REJECTED' ? 'text-red-400' : 'text-yellow-400'
                      )}>{ord.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] text-[#8b949e] mb-1 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  )
}
