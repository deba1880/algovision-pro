import { AppDispatch } from '../store'
import { setIndices, setBreadth, setFiiDii, setConnected } from '../store/slices/marketSlice'
import { setSignal } from '../store/slices/signalSlice'
import { setRobotStatus, addRobotTrade, updateRobotExit, setRobotAnalysis } from '../store/slices/robotSlice'

const _apiBase = import.meta.env.VITE_API_BASE_URL ?? ''
const WS_BASE = _apiBase
  ? _apiBase.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:')
  : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`

let marketSocket: WebSocket | null = null
let _soundEnabled = true

export function setSoundEnabled(v: boolean) { _soundEnabled = v }
export function isSoundEnabled() { return _soundEnabled }

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
        case 'robot_status':
          dispatch(setRobotStatus(msg.data))
          break
        case 'robot_trade':
          dispatch(addRobotTrade(msg.data))
          playSound('entry')
          break
        case 'robot_exit': {
          dispatch(updateRobotExit(msg.data))
          const isProfit = (msg.data.pnl ?? 0) >= 0
          playSound(isProfit ? 'exit_profit' : 'exit_sl')
          break
        }
        case 'robot_analysis':
          dispatch(setRobotAnalysis(msg.data))
          break
        case 'ping':
          break
      }
    } catch { }
  }

  marketSocket.onclose = () => {
    dispatch(setConnected(false))
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

// ─── Sound Alerts ─────────────────────────────────────────────────────────────

let _audioCtx: AudioContext | null = null

type SoundType = 'entry' | 'exit_profit' | 'exit_sl'

interface SoundConfig {
  freqs: number[]
  freqTimes: number[]
  gain: number
  duration: number
  freqRamp?: number
}

const SOUND_CONFIGS: Record<SoundType, SoundConfig> = {
  entry:       { freqs: [660, 880],      freqTimes: [0, 0.15],        gain: 0.25, duration: 0.45 },
  exit_profit: { freqs: [523, 659, 784], freqTimes: [0, 0.12, 0.24],  gain: 0.20, duration: 0.50 },
  exit_sl:     { freqs: [300],           freqTimes: [0],               gain: 0.20, duration: 0.70, freqRamp: 150 },
}

function playSound(type: SoundType) {
  if (!_soundEnabled) return
  try {
    if (!_audioCtx) _audioCtx = new AudioContext()
    const ctx = _audioCtx
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)

    const cfg = SOUND_CONFIGS[type]
    cfg.freqs.forEach((f, i) => osc.frequency.setValueAtTime(f, ctx.currentTime + cfg.freqTimes[i]))
    if (cfg.freqRamp !== undefined)
      osc.frequency.exponentialRampToValueAtTime(cfg.freqRamp, ctx.currentTime + cfg.duration)
    gain.gain.setValueAtTime(cfg.gain, ctx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + cfg.duration)
    osc.start()
    osc.stop(ctx.currentTime + cfg.duration)
  } catch { }
}
