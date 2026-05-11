import { createSlice, PayloadAction } from '@reduxjs/toolkit'

export interface Signal {
  symbol: string
  exchange: string
  timeframe: string
  signal_type: 'BUY' | 'SELL' | 'HOLD'
  strength: number
  entry_price: number
  stop_loss: number
  target_1: number
  target_2: number
  target_3: number
  risk_reward: number
  strategy: string
  reasons: string[]
  warnings: string[]
  generated_at: string
}

interface SignalState {
  current: Signal | null
  history: Signal[]
  loading: boolean
  error: string | null
}

const initialState: SignalState = {
  current: null,
  history: [],
  loading: false,
  error: null,
}

const signalSlice = createSlice({
  name: 'signals',
  initialState,
  reducers: {
    setSignal(state, action: PayloadAction<Signal>) {
      state.current = action.payload
      state.history.unshift(action.payload)
      if (state.history.length > 50) state.history.pop()
    },
    setLoading(state, action: PayloadAction<boolean>) {
      state.loading = action.payload
    },
    setError(state, action: PayloadAction<string | null>) {
      state.error = action.payload
    },
  },
})

export const { setSignal, setLoading, setError } = signalSlice.actions
export default signalSlice.reducer
