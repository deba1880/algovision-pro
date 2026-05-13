import axios from 'axios'

const http = axios.create({
  baseURL: `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1`,
  timeout: 10_000,
})

export const api = {
  // Market data
  getQuote: (symbol: string, exchange = 'NSE') =>
    http.get(`/market/quote/${symbol}?exchange=${exchange}`).then(r => r.data),

  getCandles: (symbol: string, exchange: string, timeframe: string, limit = 500) =>
    http.get(`/market/candles/${symbol}?exchange=${exchange}&timeframe=${timeframe}&limit=${limit}`)
      .then(r => r.data),

  getOptionsChain: (symbol: string) =>
    http.get(`/market/options-chain/${symbol}`).then(r => r.data.data),

  getIndices: () =>
    http.get('/market/indices').then(r => r.data.data),

  getBreadth: () =>
    http.get('/market/breadth').then(r => r.data),

  getFiiDii: () =>
    http.get('/market/fii-dii').then(r => r.data),

  getEvents: (daysAhead = 30) =>
    http.get(`/market/events?days_ahead=${daysAhead}`).then(r => r.data),

  getSignal: (symbol: string, exchange: string, timeframe: string) =>
    http.get(`/market/signal/${symbol}?exchange=${exchange}&timeframe=${timeframe}`).then(r => r.data),

  searchSymbols: (q: string) =>
    http.get(`/market/search?q=${encodeURIComponent(q)}`).then(r => r.data),

  // Trading
  placeOrder: (order: any) =>
    http.post('/trading/orders', order).then(r => r.data),

  cancelOrder: (id: number) =>
    http.delete(`/trading/orders/${id}`).then(r => r.data),

  getPositions: () =>
    http.get('/trading/positions').then(r => r.data),

  getOrders: () =>
    http.get('/trading/orders').then(r => r.data),

  // Options LTP (served from cache)
  getOptionLtp: (underlying: string, strike: number, optionType: string, expiry: string) =>
    http.get(`/market/option-ltp/${underlying}?strike=${strike}&option_type=${optionType}&expiry=${encodeURIComponent(expiry)}`)
      .then(r => r.data),

  // Backtesting
  runBacktest: (config: any) =>
    http.post('/backtest/run', config, { timeout: 90_000 }).then(r => r.data),

  // Alerts
  getAlertStatus: () =>
    http.get('/alerts/status').then(r => r.data),

  sendTestAlert: () =>
    http.post('/alerts/test').then(r => r.data),

  // Robot
  getRobotConfig: () =>
    http.get('/robot/config').then(r => r.data),
  updateRobotConfig: (config: any) =>
    http.put('/robot/config', config).then(r => r.data),
  startRobot: () =>
    http.post('/robot/start').then(r => r.data),
  stopRobot: () =>
    http.post('/robot/stop').then(r => r.data),
  getRobotStatus: () =>
    http.get('/robot/status').then(r => r.data),
  getRobotTrades: (status?: string, limit = 50) =>
    http.get(`/robot/trades?${status ? `status=${status}&` : ''}limit=${limit}`).then(r => r.data),

  // Health
  health: () =>
    http.get('/health', { baseURL: '/' }).then(r => r.data),
}
