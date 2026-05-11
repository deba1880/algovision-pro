import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface IndexData {
  name: string
  ltp: number
  change: number
  change_pct: number
  advance: number
  decline: number
}

interface Breadth {
  advances: number
  declines: number
  unchanged: number
  total: number
  ad_ratio: number
}

interface FiiDii {
  fii_net: number
  dii_net: number
  fii_buy: number
  fii_sell: number
}

interface QuoteMap {
  [symbol: string]: {
    ltp: number
    change: number
    change_pct: number
    volume: number
    oi?: number
    timestamp: string
  }
}

interface MarketState {
  indices: IndexData[]
  breadth: Breadth | null
  fiiDii: FiiDii | null
  quotes: QuoteMap
  connected: boolean
  marketStatus: 'PRE_OPEN' | 'OPEN' | 'CLOSED' | 'POST_CLOSE'
}

const initialState: MarketState = {
  indices: [],
  breadth: null,
  fiiDii: null,
  quotes: {},
  connected: false,
  marketStatus: 'CLOSED',
}

const marketSlice = createSlice({
  name: 'market',
  initialState,
  reducers: {
    setIndices(state, action: PayloadAction<IndexData[]>) {
      state.indices = action.payload
    },
    setBreadth(state, action: PayloadAction<Breadth>) {
      state.breadth = action.payload
    },
    setFiiDii(state, action: PayloadAction<FiiDii>) {
      state.fiiDii = action.payload
    },
    updateQuote(state, action: PayloadAction<{ symbol: string; data: any }>) {
      const { symbol, data } = action.payload
      state.quotes[symbol] = {
        ltp: data.ltp,
        change: data.ltp - data.close,
        change_pct: data.close ? ((data.ltp - data.close) / data.close) * 100 : 0,
        volume: data.volume,
        oi: data.oi,
        timestamp: data.timestamp,
      }
    },
    setConnected(state, action: PayloadAction<boolean>) {
      state.connected = action.payload
    },
    setMarketStatus(state, action: PayloadAction<MarketState['marketStatus']>) {
      state.marketStatus = action.payload
    },
  },
})

export const { setIndices, setBreadth, setFiiDii, updateQuote, setConnected, setMarketStatus } = marketSlice.actions
export default marketSlice.reducer
