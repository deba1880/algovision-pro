import { useEffect, useState } from 'react'
import { Calendar, AlertCircle } from 'lucide-react'
import { api } from '../services/api'
import { clsx } from 'clsx'

const IMPACT_COLORS: Record<string, string> = {
  HIGH:   'bg-red-500/20 text-red-400 border border-red-500/30',
  MEDIUM: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  LOW:    'bg-gray-500/20 text-gray-400 border border-gray-500/30',
}

export default function EventsPage() {
  const [events, setEvents] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getEvents(60).then(d => { setEvents(d.events); setLoading(false) })
  }, [])

  const grouped = events.reduce((acc: Record<string, any[]>, ev) => {
    acc[ev.date] = acc[ev.date] || []
    acc[ev.date].push(ev)
    return acc
  }, {})

  return (
    <div className="p-4 max-w-4xl">
      <div className="flex items-center gap-2 mb-4">
        <Calendar size={16} className="text-blue-400" />
        <h2 className="text-sm font-semibold text-white">Market Events Calendar</h2>
      </div>

      {loading && <p className="text-xs text-[#8b949e]">Loading events...</p>}

      {Object.entries(grouped).map(([date, evs]) => (
        <div key={date} className="mb-4">
          <div className="text-xs font-semibold text-[#8b949e] uppercase mb-2 sticky top-0 bg-[#0d1117] py-1">
            {new Date(date).toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
          <div className="space-y-1.5">
            {evs.map(ev => (
              <div key={ev.id} className="panel p-3 flex items-start gap-3">
                <div className="shrink-0 w-16 text-[10px] text-[#8b949e]">{ev.time || 'All Day'}</div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-medium text-white">{ev.title}</span>
                    {ev.symbol && <span className="text-[10px] text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">{ev.symbol}</span>}
                    <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium', IMPACT_COLORS[ev.impact] || IMPACT_COLORS.LOW)}>
                      {ev.impact}
                    </span>
                  </div>
                  {ev.description && <p className="text-[10px] text-[#8b949e]">{ev.description}</p>}
                  <div className="text-[10px] text-[#8b949e] mt-0.5">{ev.category}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {!loading && events.length === 0 && (
        <div className="flex items-center gap-2 text-xs text-[#8b949e] py-8">
          <AlertCircle size={14} />
          <span>No upcoming events found. Events are populated from NSE and RBI announcements.</span>
        </div>
      )}
    </div>
  )
}
