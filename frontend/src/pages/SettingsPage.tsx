import { useEffect, useState } from 'react'
import { Settings, CheckCircle, XCircle, Send, AlertTriangle } from 'lucide-react'
import { api } from '../services/api'
import { clsx } from 'clsx'

interface AlertStatus {
  telegram: { configured: boolean; chat_id: string | null }
  email: { configured: boolean; smtp_host: string; smtp_port: number; user: string | null }
  paper_trade_mode: boolean
  risk_controls: {
    max_daily_loss_pct: number
    max_open_positions: number
    max_order_value_inr: number
  }
}

export default function SettingsPage() {
  const [status, setStatus] = useState<AlertStatus | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ telegram_sent: boolean; email_sent: boolean } | null>(null)

  useEffect(() => {
    api.getAlertStatus().then(setStatus).catch(() => {})
  }, [])

  const sendTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.sendTestAlert()
      setTestResult(res)
    } catch { /* ignore */ }
    finally { setTesting(false) }
  }

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div className="flex items-center gap-2 mb-2">
        <Settings size={16} className="text-blue-400" />
        <h2 className="text-sm font-semibold text-white">Settings</h2>
      </div>

      {/* Alert Channels */}
      <div className="panel p-4 space-y-4">
        <h3 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider">Alert Channels</h3>

        {status ? (
          <>
            <Channel
              label="Telegram"
              configured={status.telegram.configured}
              detail={status.telegram.chat_id ? `Chat ID: ${status.telegram.chat_id}` : 'Not configured'}
              envVars={['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']}
              hint="Create a bot via @BotFather, then get your chat ID by messaging @userinfobot."
            />

            <Channel
              label="Email (SMTP)"
              configured={status.email.configured}
              detail={status.email.user
                ? `${status.email.user} via ${status.email.smtp_host}:${status.email.smtp_port}`
                : 'Not configured'}
              envVars={['SMTP_USER', 'SMTP_PASSWORD']}
              hint="Gmail: enable 2FA and generate an App Password at myaccount.google.com/apppasswords."
            />

            <button
              onClick={sendTest}
              disabled={testing || (!status.telegram.configured && !status.email.configured)}
              className="flex items-center gap-2 px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold transition-colors"
            >
              <Send size={13} />
              {testing ? 'Sending…' : 'Send Test Alert'}
            </button>

            {testResult && (
              <div className="text-xs space-y-1 mt-2">
                <Result label="Telegram" sent={testResult.telegram_sent} />
                <Result label="Email" sent={testResult.email_sent} />
              </div>
            )}
          </>
        ) : (
          <p className="text-xs text-[#8b949e]">Loading…</p>
        )}
      </div>

      {/* Risk Controls */}
      {status && (
        <div className="panel p-4 space-y-3">
          <h3 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider">Risk Controls</h3>
          <div className="grid grid-cols-2 gap-3">
            <Stat label="Max Daily Loss" value={`${status.risk_controls.max_daily_loss_pct}%`} />
            <Stat label="Max Open Positions" value={String(status.risk_controls.max_open_positions)} />
            <Stat label="Max Order Value" value={`₹${status.risk_controls.max_order_value_inr.toLocaleString('en-IN')}`} />
            <Stat label="Trading Mode" value={status.paper_trade_mode ? 'Paper' : 'Live'} accent={!status.paper_trade_mode} />
          </div>
          <p className="text-[10px] text-[#8b949e] leading-relaxed">
            Risk controls are set in <code className="bg-[#0d1117] px-1 rounded">.env</code> and take effect on restart.
          </p>
        </div>
      )}

      {/* Configuration Guide */}
      <div className="panel p-4">
        <h3 className="text-xs font-semibold text-[#8b949e] uppercase tracking-wider mb-3">Configuration</h3>
        <p className="text-[10px] text-[#8b949e] leading-relaxed mb-3">
          Edit <code className="bg-[#0d1117] px-1 rounded">backend/.env</code> to configure alerts and risk controls.
          Restart the backend server after making changes.
        </p>
        <pre className="text-[10px] bg-[#0d1117] rounded p-3 text-green-300 overflow-auto leading-relaxed">{`# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789

# Email (Gmail example)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password

# Risk
MAX_DAILY_LOSS_PCT=2.0
MAX_OPEN_POSITIONS=5
MAX_ORDER_VALUE_INR=50000
PAPER_TRADE_MODE=true`}</pre>
      </div>
    </div>
  )
}

function Channel({ label, configured, detail, envVars, hint }: {
  label: string
  configured: boolean
  detail: string
  envVars: string[]
  hint: string
}) {
  return (
    <div className="border border-[#30363d] rounded p-3 space-y-1.5">
      <div className="flex items-center gap-2">
        {configured
          ? <CheckCircle size={13} className="text-green-400 shrink-0" />
          : <XCircle size={13} className="text-[#8b949e] shrink-0" />}
        <span className={clsx('text-xs font-medium', configured ? 'text-white' : 'text-[#8b949e]')}>
          {label}
        </span>
        <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium ml-auto',
          configured ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
        )}>
          {configured ? 'Configured' : 'Not Set'}
        </span>
      </div>
      <p className="text-[10px] text-[#8b949e]">{detail}</p>
      {!configured && (
        <div className="flex items-start gap-1.5 mt-1">
          <AlertTriangle size={10} className="text-yellow-400 mt-0.5 shrink-0" />
          <div className="text-[10px] text-[#8b949e]">
            Set <code className="bg-[#0d1117] px-0.5 rounded">{envVars.join(', ')}</code> in .env · {hint}
          </div>
        </div>
      )}
    </div>
  )
}

function Result({ label, sent }: { label: string; sent: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      {sent
        ? <CheckCircle size={11} className="text-green-400" />
        : <XCircle size={11} className="text-red-400" />}
      <span className={sent ? 'text-green-400' : 'text-red-400'}>
        {label}: {sent ? 'Sent successfully' : 'Failed (check config)'}
      </span>
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="border border-[#30363d] rounded p-2">
      <div className="text-[10px] text-[#8b949e] mb-0.5">{label}</div>
      <div className={clsx('text-xs font-semibold font-mono', accent ? 'text-orange-400' : 'text-white')}>
        {value}
      </div>
    </div>
  )
}
