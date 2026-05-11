import { AppDispatch } from '../store'
import { updateQuote, setIndices, setBreadth, setFiiDii, setConnected } from '../store/slices/marketSlice'
import { setSignal } from '../store/slices/signalSlice'

const _apiBase = import.meta.env.VITE_API_BASE_URL ?? ''
const WS_BASE = _apiBase
  ? _apiBase.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:')
  : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`

let marketSocket: WebSocket | null = null

export function initWebSocket(dispatch: AppDispatch) {
  connectMarketSocket(dispatch)
}

function connectMarketSocket(dispatch: AppDispatch) {
  if (marketSocket?.readyState === WebSocket.OPEN) return

  marketSocket = new WebSocket(`${WS_BASE}/ws/market`)

  marketSocket.onopen = () => {
    dispatch(setConnected(true))
    console.log('Market WebSocket connected')
  }

  marketSocket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      switch (msg.type) {
        case 'indices':
          dispatch(setIndices(msg.data))
          break
        case 'breadth':
          dispatch(setBreadth(msg.data))
          break
        case 'fii_dii':
          dispatch(setFiiDii(msg.data))
          break
        case 'signal':
          dispatch(setSignal(msg.data))
          break
        case 'ping':
          break
      }
    } catch { }
  }

  marketSocket.onclose = () => {
    dispatch(setConnected(false))
    // Reconnect after 5 seconds
    setTimeout(() => connectMarketSocket(dispatch), 5000)
  }

  marketSocket.onerror = () => {
    dispatch(setConnected(false))
  }
}

export function connectTickWebSocket(symbol: string, onTick: (tick: any) => void): () => void {
  const ws = new WebSocket(`${WS_BASE}/ws/ticks/${symbol}`)

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      if (msg.type === 'tick' && msg.data) {
        onTick(msg.data)
      }
    } catch { }
  }

  ws.onerror = (e) => console.error('Tick WS error:', e)

  return () => {
    ws.onmessage = null
    ws.onerror = null
    ws.onclose = null
    ws.close()
  }
}
