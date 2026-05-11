import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface ChartSymbol {
  symbol: string
  exchange: string
  name: string
  token: string
  segment: string
}

type Timeframe = '1m' | '3m' | '5m' | '10m' | '15m' | '30m' | '1h' | '2h' | '4h' | '1d' | '1w'

interface ChartState {
  activeSymbol: ChartSymbol
  timeframe: Timeframe
  indicators: string[]
  showSMCZones: boolean
  showSignals: boolean
  showLiquidityZones: boolean
  layout: 1 | 2 | 4
}

const initialState: ChartState = {
  activeSymbol: {
    symbol: 'NIFTY',
    exchange: 'NSE',
    name: 'NIFTY 50',
    token: '26000',
    segment: 'IDX',
  },
  timeframe: '15m',
  indicators: ['EMA20', 'EMA50', 'VWAP'],
  showSMCZones: true,
  showSignals: true,
  showLiquidityZones: true,
  layout: 1,
}

const chartSlice = createSlice({
  name: 'chart',
  initialState,
  reducers: {
    setSymbol(state, action: PayloadAction<ChartSymbol>) {
      state.activeSymbol = action.payload
    },
    setTimeframe(state, action: PayloadAction<Timeframe>) {
      state.timeframe = action.payload
    },
    toggleIndicator(state, action: PayloadAction<string>) {
      const idx = state.indicators.indexOf(action.payload)
      if (idx === -1) {
        state.indicators.push(action.payload)
      } else {
        state.indicators.splice(idx, 1)
      }
    },
    toggleSMCZones(state) { state.showSMCZones = !state.showSMCZones },
    toggleSignals(state) { state.showSignals = !state.showSignals },
    toggleLiquidityZones(state) { state.showLiquidityZones = !state.showLiquidityZones },
    setLayout(state, action: PayloadAction<1 | 2 | 4>) {
      state.layout = action.payload
    },
  },
})

export const {
  setSymbol, setTimeframe, toggleIndicator, toggleSMCZones,
  toggleSignals, toggleLiquidityZones, setLayout,
} = chartSlice.actions
export default chartSlice.reducer
