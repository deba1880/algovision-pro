import { useEffect, useRef, useState } from 'react'
import { createChart, IChartApi, ISeriesApi, ColorType, LineSeries, UTCTimestamp } from 'lightweight-charts'
import { api } from '../../services/api'
import { X } from 'lucide-react'

interface Props {
  underlying: string
  strike: number
  optionType: 'CE' | 'PE'
  expiry: string
  initialLtp: number
  onClose: () => void
}

export default function OptionLtpChart({ underlying, strike, optionType, expiry, initialLtp, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const [currentLtp, setCurrentLtp] = useState(initialLtp)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#0d1117' },
        textColor: '#8b949e',
      },
      grid: { vertLines: { color: '#1c2128' }, horzLines: { color: '#1c2128' } },
      rightPriceScale: { borderColor: '#30363d' },
      timeScale: { borderColor: '#30363d', timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: '#30363d' }, horzLine: { color: '#30363d' } },
      handleScroll: true,
      handleScale: true,
    })

    const series = chart.addSeries(LineSeries, {
      color: optionType === 'CE' ? '#3fb950' : '#f85149',
      lineWidth: 2,
      priceLineVisible: true,
      lastValueVisible: true,
    })

    // Seed with initial point
    const now = Math.floor(Date.now() / 1000) as UTCTimestamp
    series.setData([{ time: now, value: initialLtp }])
    chart.timeScale().fitContent()

    chartRef.current = chart
    seriesRef.current = series

    // Poll every 30 seconds
    const poll = setInterval(async () => {
      try {
        const d = await api.getOptionLtp(underlying, strike, optionType, expiry)
        const point = { time: Math.floor(Date.now() / 1000) as UTCTimestamp, value: d.ltp as number }
        seriesRef.current?.update(point)
        setCurrentLtp(d.ltp)
      } catch { /* cache may be cold outside market hours */ }
    }, 30_000)

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    if (containerRef.current) ro.observe(containerRef.current)

    return () => {
      clearInterval(poll)
      ro.disconnect()
      chart.remove()
    }
  }, [underlying, strike, optionType, expiry, initialLtp])

  const color = optionType === 'CE' ? 'text-green-400' : 'text-red-400'

  return (
    <div className="flex flex-col h-full bg-[#0d1117] border-l border-[#30363d]">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-[#161b22] border-b border-[#30363d] shrink-0">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-bold font-mono ${color}`}>
            {underlying} {strike} {optionType}
          </span>
          <span className="text-xs text-[#8b949e]">{expiry}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-sm font-mono font-semibold ${color}`}>
            ₹{currentLtp.toFixed(2)}
          </span>
          <button onClick={onClose} className="text-[#8b949e] hover:text-white">
            <X size={14} />
          </button>
        </div>
      </div>
      {/* Chart */}
      <div ref={containerRef} className="flex-1 w-full" />
    </div>
  )
}
