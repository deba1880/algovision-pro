import { createSlice, PayloadAction } from '@reduxjs/toolkit'

export interface RobotConfig {
  symbols: string[]
  lot_sizes: Record<string, number>
  max_lots_per_trade: number
  capital_per_trade_pct: number
  strike_selection: string
  expiry_preference: string
  timeframe: string
  target1_pct: number
  target2_pct: number
  target3_pct: number
  stoploss_pct: number
  trail_sl_after_t1: boolean
  exit1_qty_pct: number
  exit2_qty_pct: number
  exit3_qty_pct: number
  max_trades_per_day: number
  auto_square_off_time: string
  enabled: boolean
}

export interface RobotTrade {
  id: string
  symbol: string
  option_type: 'CE' | 'PE'
  strike: number
  expiry: string
  entry_price: number
  current_price: number
  quantity: number
  lots: number
  sl_price: number
  t1_price: number
  t2_price: number
  t3_price: number
  t1_hit: boolean
  t2_hit: boolean
  status: string
  entry_time: string
  exit_time: string | null
  exit_price: number | null
  pnl: number
  pnl_pct: number
  reasons: string[]
}

export interface RobotAnalysis {
  symbol: string
  trend?: string
  signal_type?: string
  signal_strength?: number
  underlying_price?: number
  reasons?: string[]
  warnings?: string[]
  event?: string
  trade_id?: string
  price?: number
  timestamp: string
}

export interface RobotSoundEvent {
  type: 'entry' | 'exit_profit' | 'exit_sl'
  trade: RobotTrade
  at: number
}

interface RobotState {
  running: boolean
  config: RobotConfig | null
  activeTrades: RobotTrade[]
  tradeHistory: RobotTrade[]
  todayPnl: number
  todayTrades: number
  analysis: Record<string, RobotAnalysis>
  soundEvent: RobotSoundEvent | null
}

const initialState: RobotState = {
  running: false,
  config: null,
  activeTrades: [],
  tradeHistory: [],
  todayPnl: 0,
  todayTrades: 0,
  analysis: {},
  soundEvent: null,
}

const robotSlice = createSlice({
  name: 'robot',
  initialState,
  reducers: {
    setRobotStatus(state, action: PayloadAction<{
      running: boolean
      active_trades: RobotTrade[]
      trade_history: RobotTrade[]
      today_pnl: number
      today_trades: number
    }>) {
      const { running, active_trades, trade_history, today_pnl, today_trades } = action.payload
      state.running = running
      state.activeTrades = active_trades ?? []
      state.tradeHistory = trade_history ?? []
      state.todayPnl = today_pnl ?? 0
      state.todayTrades = today_trades ?? 0
    },

    setRobotConfig(state, action: PayloadAction<RobotConfig>) {
      state.config = action.payload
    },

    addRobotTrade(state, action: PayloadAction<RobotTrade>) {
      // Remove if already present (update), then prepend
      state.activeTrades = [action.payload, ...state.activeTrades.filter(t => t.id !== action.payload.id)]
      state.todayTrades += 1
      state.soundEvent = { type: 'entry', trade: action.payload, at: Date.now() }
    },

    updateRobotExit(state, action: PayloadAction<RobotTrade>) {
      state.activeTrades = state.activeTrades.filter(t => t.id !== action.payload.id)
      state.tradeHistory = [action.payload, ...state.tradeHistory].slice(0, 100)
      state.todayPnl += action.payload.pnl
      const isProfit = action.payload.pnl >= 0
      state.soundEvent = {
        type: isProfit ? 'exit_profit' : 'exit_sl',
        trade: action.payload,
        at: Date.now(),
      }
    },

    setRobotAnalysis(state, action: PayloadAction<RobotAnalysis>) {
      state.analysis[action.payload.symbol] = action.payload
    },

    clearSoundEvent(state) {
      state.soundEvent = null
    },
  },
})

export const {
  setRobotStatus,
  setRobotConfig,
  addRobotTrade,
  updateRobotExit,
  setRobotAnalysis,
  clearSoundEvent,
} = robotSlice.actions

export default robotSlice.reducer
