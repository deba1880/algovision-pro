import { useEffect, useRef, useCallback } from 'react'
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LineData,
  ColorType,
  CrosshairMode,
  UTCTimestamp,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
} from 'lightweight-charts'
import { useAppSelector, useAppDispatch } from '../../store/hooks'
import { api } from '../../services/api'
import { connectTickWebSocket } from '../../services/websocket'

const CHART_COLORS = {
  bg:          '#0d1117',
  grid:        '#1c2128',
  border:      '#30363d',
  text:        '#8b949e',
  upColor:     '#3fb950',
  downColor:   '#f85149',
  wickUp:      '#3fb950',
  wickDown:    '#f85149',
  volume_up:   'rgba(63,185,80,0.3)',
  volume_down: 'rgba(248,81,73,0.3)',
  ema20:       '#58a6ff',
  ema50:       '#d29922',
  ema200:      '#ff7b72',
  vwap:        '#bc8cff',
}

interface SMCZone {
  zone_type: string
  price_top: number
  price_bottom: number
  candle_time: string
  strength: number
  description: string
}

interface ChartProps {
  height?: number
}

export default function TradingChart({ height = 600 }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const ema20Ref  = useRef<ISeriesApi<'Line'> | null>(null)
  const ema50Ref  = useRef<ISeriesApi<'Line'> | null>(null)
  const ema200Ref = useRef<ISeriesApi<'Line'> | null>(null)
  const vwapRef   = useRef<ISeriesApi<'Line'> | null>(null)
  const smcBoxRefs = useRef<any[]>([])
  const wsCleanup = useRef<(() => void) | null>(null)

  const { activeSymbol, timeframe, indicators, showSMCZones, showSignals } = useAppSelector(s => s.chart)
  const dispatch = useAppDispatch()

  // ─── Initialize Chart ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.bg },
        textColor: CHART_COLORS.text,
      },
      grid: {
        vertLines: { color: CHART_COLORS.grid },
        horzLines: { color: CHART_COLORS.grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: CHART_COLORS.border,
        textColor: CHART_COLORS.text,
      },
      timeScale: {
        borderColor: CHART_COLORS.border,
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height,
    })

    chartRef.current = chart

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:          CHART_COLORS.upColor,
      downColor:        CHART_COLORS.downColor,
      borderUpColor:    CHART_COLORS.upColor,
      borderDownColor:  CHART_COLORS.downColor,
      wickUpColor:      CHART_COLORS.wickUp,
      wickDownColor:    CHART_COLORS.wickDown,
    })
    candleRef.current = candleSeries

    // Volume histogram (sub-pane via price scale)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })
    volumeRef.current = volumeSeries

    // EMA 20
    ema20Ref.current = chart.addSeries(LineSeries, {
      color: CHART_COLORS.ema20,
      lineWidth: 1,
      title: 'EMA 20',
      crosshairMarkerVisible: false,
      lastValueVisible: true,
    })

    // EMA 50
    ema50Ref.current = chart.addSeries(LineSeries, {
      color: CHART_COLORS.ema50,
      lineWidth: 1,
      title: 'EMA 50',
      crosshairMarkerVisible: false,
      lastValueVisible: true,
    })

    // EMA 200
    ema200Ref.current = chart.addSeries(LineSeries, {
      color: CHART_COLORS.ema200,
      lineWidth: 1,
      title: 'EMA 200',
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      visible: false,
    })

    // VWAP
    vwapRef.current = chart.addSeries(LineSeries, {
      color: CHART_COLORS.vwap,
      lineWidth: 1,
      lineStyle: 2, // dashed
      title: 'VWAP',
      crosshairMarkerVisible: false,
    })

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [height])

  // ─── Load Data on Symbol / Timeframe Change ────────────────────────────────
  useEffect(() => {
    loadCandles()
    loadSMCZones()

    // Clean up previous WS and subscribe to new symbol
    if (wsCleanup.current) wsCleanup.current()
    wsCleanup.current = connectTickWebSocket(activeSymbol.symbol, (tick) => {
      if (candleRef.current && tick.ltp) {
        const now = Math.floor(Date.now() / 1000) as UTCTimestamp
        candleRef.current.update({
          time: now,
          open: tick.open || tick.ltp,
          high: tick.high || tick.ltp,
          low: tick.low || tick.ltp,
          close: tick.ltp,
        })
      }
    })

    return () => {
      if (wsCleanup.current) wsCleanup.current()
    }
  }, [activeSymbol.symbol, activeSymbol.exchange, timeframe])

  // ─── Load OHLCV Candles ────────────────────────────────────────────────────
  const loadCandles = useCallback(async () => {
    try {
      const data = await api.getCandles(activeSymbol.symbol, activeSymbol.exchange, timeframe)
      const candles: CandlestickData[] = data.candles.map((c: any) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))

      const volumes = data.candles.map((c: any) => ({
        time: c.time as UTCTimestamp,
        value: c.volume,
        color: c.close >= c.open ? CHART_COLORS.volume_up : CHART_COLORS.volume_down,
      }))

      candleRef.current?.setData(candles)
      volumeRef.current?.setData(volumes)

      // Calculate and plot EMAs
      const closes = data.candles.map((c: any) => c.close)
      plotEMA(data.candles, closes, 20, ema20Ref.current)
      plotEMA(data.candles, closes, 50, ema50Ref.current)
      plotEMA(data.candles, closes, 200, ema200Ref.current)
      plotVWAP(data.candles, vwapRef.current)

      chartRef.current?.timeScale().fitContent()
    } catch (err) {
      console.error('Failed to load candles:', err)
    }
  }, [activeSymbol, timeframe])

  // ─── Load SMC Zones ────────────────────────────────────────────────────────
  const loadSMCZones = useCallback(async () => {
    if (!showSMCZones || !chartRef.current) return
    try {
      const signal = await api.getSignal(activeSymbol.symbol, activeSymbol.exchange, timeframe)
      // Clear previous zone primitives (lightweight-charts v5 uses series primitives)
      // In a production build, use IPriceLine or custom primitives for zone rendering
      // For now, we add horizontal lines for key levels
      if (signal.stop_loss && candleRef.current) {
        candleRef.current.createPriceLine({
          price: signal.entry_price,
          color: '#58a6ff',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `Entry ${signal.signal_type}`,
        })
        candleRef.current.createPriceLine({
          price: signal.stop_loss,
          color: '#f85149',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'SL',
        })
        candleRef.current.createPriceLine({
          price: signal.target_1,
          color: '#3fb950',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'T1',
        })
        candleRef.current.createPriceLine({
          price: signal.target_2,
          color: '#3fb950',
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: 'T2',
        })
      }
    } catch {
      // Signal not yet available
    }
  }, [activeSymbol, timeframe, showSMCZones])

  // ─── Show/Hide Indicators ──────────────────────────────────────────────────
  useEffect(() => {
    ema20Ref.current?.applyOptions({ visible: indicators.includes('EMA20') })
    ema50Ref.current?.applyOptions({ visible: indicators.includes('EMA50') })
    ema200Ref.current?.applyOptions({ visible: indicators.includes('EMA200') })
    vwapRef.current?.applyOptions({ visible: indicators.includes('VWAP') })
  }, [indicators])

  return (
    <div
      ref={containerRef}
      className="w-full rounded"
      style={{ height, background: CHART_COLORS.bg }}
    />
  )
}

// ─── Indicator Calculations ────────────────────────────────────────────────────

function plotEMA(candles: any[], closes: number[], period: number, series: ISeriesApi<'Line'> | null) {
  if (!series || candles.length < period) return
  const k = 2 / (period + 1)
  let ema = closes[0]
  const data: LineData[] = []
  candles.forEach((c, i) => {
    if (i === 0) { ema = closes[0]; return }
    ema = closes[i] * k + ema * (1 - k)
    if (i >= period - 1) {
      data.push({ time: c.time as UTCTimestamp, value: ema })
    }
  })
  series.setData(data)
}

function plotVWAP(candles: any[], series: ISeriesApi<'Line'> | null) {
  if (!series || !candles.length) return
  let cumTV = 0, cumV = 0
  const data: LineData[] = candles.map(c => {
    const typical = (c.high + c.low + c.close) / 3
    cumTV += typical * c.volume
    cumV  += c.volume
    return { time: c.time as UTCTimestamp, value: cumV ? cumTV / cumV : c.close }
  })
  series.setData(data)
}
