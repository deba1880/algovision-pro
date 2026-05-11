import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface Position {
  id: number
  symbol: string
  exchange: string
  product: string
  quantity: number
  avg_price: number
  ltp: number
  pnl: number
  pnl_pct: number
  opened_at: string
}

interface Order {
  id: number
  symbol: string
  exchange: string
  transaction: string
  order_type: string
  quantity: number
  price: number
  status: string
  placed_at: string
}

interface TradingState {
  positions: Position[]
  orders: Order[]
  isPaperMode: boolean
  dailyPnl: number
  totalPnl: number
}

const initialState: TradingState = {
  positions: [],
  orders: [],
  isPaperMode: true,
  dailyPnl: 0,
  totalPnl: 0,
}

const tradingSlice = createSlice({
  name: 'trading',
  initialState,
  reducers: {
    setPositions(state, action: PayloadAction<Position[]>) {
      state.positions = action.payload
      state.dailyPnl = action.payload.reduce((sum, p) => sum + (p.pnl || 0), 0)
    },
    setOrders(state, action: PayloadAction<Order[]>) {
      state.orders = action.payload
    },
    setPaperMode(state, action: PayloadAction<boolean>) {
      state.isPaperMode = action.payload
    },
  },
})

export const { setPositions, setOrders, setPaperMode } = tradingSlice.actions
export default tradingSlice.reducer
