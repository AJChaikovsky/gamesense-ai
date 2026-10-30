import type { AppMetrics, Hotkey, HotkeyStatus } from '@shared/bridge'
import {
  Activity,
  Cpu,
  DollarSign,
  Eye,
  EyeOff,
  Film,
  Gamepad2,
  Gauge,
  Pause,
  Play,
  Sparkles,
  Timer
} from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { type LinkState, useEngine } from './hooks/useEngine'
import { formatUptime } from './lib/engineClient'
import { cn } from './lib/utils'

const LINK_LABEL: Record<LinkState, string> = {
  starting: 'Starting engine',
  connecting: 'Connecting',
  connected: 'Engine connected',
  disconnected: 'Reconnecting',
  failed: 'Engine failed'
}

/** RAM budget for the Electron shell before we switch to Tauri (ADR-002). */
const RAM_BUDGET_MB = 300

function StatusDot({ link }: { link: LinkState }): ReactNode {
  const color =
    link === 'connected' ? 'bg-ok' : link === 'failed' ? 'bg-danger' : 'bg-warn animate-pulse'
  return <span className={cn('inline-block size-2.5 rounded-full', color)} />
}

function Stat({
  icon,
  label,
  value,
  hint,
  tone
}: {
  icon: ReactNode
  label: string
  value: string
  hint?: string
  tone?: 'warn' | 'danger'
}): ReactNode {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center gap-2 text-sm text-muted">
        {icon}
        {label}
      </div>
      <div
        className={cn(
          'mt-2 truncate text-2xl font-semibold tabular-nums',
          tone === 'warn' && 'text-warn',
          tone === 'danger' && 'text-danger'
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-1 truncate text-xs text-muted">{hint}</div>}
    </div>
  )
}

function useAppMetrics(): AppMetrics | undefined {
  const [metrics, setMetrics] = useState<AppMetrics>()
  useEffect(() => {
    const read = (): void => void window.gamesense.getAppMetrics().then(setMetrics)
    read()
    const id = setInterval(read, 2000)
    return () => clearInterval(id)
  }, [])
  return metrics
}

const HOTKEY_NAMES: Record<Hotkey, string> = {
  dismiss: 'Dismiss',
  useful: 'Useful',
  not_useful: 'Not useful',
  pause: 'Pause'
}

/** Which hotkeys registered, and the last press the app actually received. */
function useHotkeyDiagnostics(): {
  status?: Record<Hotkey, HotkeyStatus>
  last?: { hotkey: Hotkey; at: Date }
} {
  const [status, setStatus] = useState<Record<Hotkey, HotkeyStatus>>()
  const [last, setLast] = useState<{ hotkey: Hotkey; at: Date }>()
  useEffect(() => {
    void window.gamesense.getHotkeyStatus().then(setStatus)
    return window.gamesense.onHotkey((hotkey) => setLast({ hotkey, at: new Date() }))
  }, [])
  return { status, last }
}

function money(usd: number): string {
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`
}

export default function App(): ReactNode {
  const { link, error, heartbeat, tips, lastStatus, send } = useEngine()
  const metrics = useAppMetrics()
  const [overlayVisible, setOverlayVisible] = useState(true)
  const capture = heartbeat?.capture
  const coach = heartbeat?.coaching
  const hotkeys = useHotkeyDiagnostics()

  const toggleOverlay = (): void => {
    const next = !overlayVisible
    setOverlayVisible(next)
    void window.gamesense.setOverlayVisible(next)
  }

  return (
    <main className="mx-auto flex min-h-full max-w-5xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">GameSense</h1>
          <p className="text-sm text-muted">Developer dashboard · Milestone 1</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleOverlay}
            className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-sm hover:bg-border"
          >
            {overlayVisible ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
            Overlay {overlayVisible ? 'on' : 'off'}
          </button>
          <button
            type="button"
            disabled={!coach}
            onClick={() => send({ type: 'control', action: coach?.paused ? 'resume' : 'pause' })}
            className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-sm hover:bg-border disabled:opacity-40"
          >
            {coach?.paused ? <Play className="size-4" /> : <Pause className="size-4" />}
            {coach?.paused ? 'Resume coaching' : 'Pause coaching'}
          </button>
          <div className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-sm">
            <StatusDot link={link} />
            {LINK_LABEL[link]}
          </div>
        </div>
      </header>

      {error && (
        <div className="rounded-xl border border-danger/40 bg-danger/10 p-4 text-sm">
          <p className="font-medium">The engine could not start.</p>
          <p className="mt-1 text-muted">{error}</p>
          <p className="mt-2 text-muted">
            Check that <code>uv</code> is installed and run <code>uv sync</code> at the repo root.
          </p>
        </div>
      )}
      {lastStatus && lastStatus.level !== 'ok' && (
        <div className="rounded-xl border border-warn/40 bg-warn/10 p-4 text-sm">{lastStatus.message}</div>
      )}
      {coach && !coach.live_allowed && (
        <div className="rounded-xl border border-danger/40 bg-danger/10 p-4 text-sm">
          Live coaching is off for {coach.game_name}. {coach.policy_reason}
        </div>
      )}

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          icon={<Gamepad2 className="size-4" />}
          label="Game"
          value={coach?.game_name ?? '—'}
          hint={coach ? `${coach.provider} · ${coach.model}` : undefined}
        />
        <Stat
          icon={<Sparkles className="size-4" />}
          label="Tips / model calls"
          value={coach ? `${coach.tips_delivered} / ${coach.calls}` : '—'}
          hint={coach?.last_latency_ms != null ? `last call ${coach.last_latency_ms} ms` : undefined}
        />
        <Stat
          icon={<DollarSign className="size-4" />}
          label="Spend (last hour)"
          value={coach ? money(coach.spend_usd_last_hour) : '—'}
          hint={coach ? `cap ${money(coach.hourly_budget_usd)}/h · session ${money(coach.spend_usd)}` : undefined}
          tone={coach && coach.spend_usd_last_hour >= coach.hourly_budget_usd * 0.8 ? 'warn' : undefined}
        />
        <Stat
          icon={<Cpu className="size-4" />}
          label="App memory"
          value={metrics ? `${metrics.memoryMb} MB` : '—'}
          hint={metrics ? `${metrics.processCount} processes · ${metrics.cpuPercent}% CPU · budget ${RAM_BUDGET_MB} MB` : undefined}
          tone={metrics && metrics.memoryMb > RAM_BUDGET_MB ? 'danger' : undefined}
        />
        <Stat
          icon={<Timer className="size-4" />}
          label="Uptime"
          value={heartbeat ? formatUptime(heartbeat.uptime_seconds) : '—'}
        />
        <Stat
          icon={<Film className="size-4" />}
          label="Capture"
          value={capture ? (capture.running ? capture.source : 'idle') : '—'}
          hint={capture?.frame_width ? `${capture.frame_width}×${capture.frame_height}` : undefined}
        />
        <Stat
          icon={<Gauge className="size-4" />}
          label="Sample rate"
          value={capture ? `${capture.fps.toFixed(1)} fps` : '—'}
          hint={capture ? `${capture.buffered_frames} frames buffered` : undefined}
        />
        <Stat
          icon={<Activity className="size-4" />}
          label="Coach"
          value={coach ? (coach.paused ? 'paused' : coach.in_flight ? 'thinking' : 'watching') : '—'}
        />
      </section>

      <section className="rounded-xl border border-border bg-surface p-4">
        <h2 className="text-sm font-medium text-muted">Recent tips</h2>
        {tips.length === 0 ? (
          <p className="mt-3 text-sm text-muted">
            No tips yet. The coach stays quiet until something worth saying happens.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-border">
            {tips.slice(0, 8).map((t) => (
              <li key={t.decision.id} className="flex items-baseline justify-between gap-4 py-2 text-sm">
                <span>
                  <span className="font-medium">{t.decision.message}</span>
                  {t.decision.detail && <span className="text-muted"> · {t.decision.detail}</span>}
                </span>
                <span className="shrink-0 text-xs text-muted">
                  {t.decision.priority} · {new Date(t.timestamp).toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-border bg-surface p-4 text-sm">
        <h2 className="font-medium text-muted">Capture source</h2>
        <p className="mt-2 break-all">
          {capture?.target ?? 'No capture source. Run "npm run sample-clip" to create a demo clip.'}
        </p>
        <h2 className="mt-4 font-medium text-muted">Overlay hotkeys</h2>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-muted">
          {(Object.keys(HOTKEY_NAMES) as Hotkey[]).map((hotkey) => {
            const ok = hotkeys.status?.[hotkey].registered
            return (
              <li key={hotkey} className="flex items-center gap-1.5">
                <span
                  className={cn(
                    'size-1.5 rounded-full',
                    ok === undefined ? 'bg-muted' : ok ? 'bg-ok' : 'bg-danger'
                  )}
                  title={ok === false ? 'Not registered: another app uses this shortcut' : 'Registered'}
                />
                {HOTKEY_NAMES[hotkey]} <kbd>{hotkeys.status?.[hotkey].accelerator ?? '…'}</kbd>
              </li>
            )
          })}
        </ul>
        <p className="mt-1 text-xs text-muted">
          {hotkeys.last
            ? `Last hotkey received: ${HOTKEY_NAMES[hotkeys.last.hotkey]} at ${hotkeys.last.at.toLocaleTimeString()}`
            : 'No hotkey presses received yet.'}
          {hotkeys.status && Object.values(hotkeys.status).some((h) => !h.registered)
            ? ' A red dot means another app holds that shortcut.'
            : ''}
        </p>
      </section>
    </main>
  )
}
