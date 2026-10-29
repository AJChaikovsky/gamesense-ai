import { Activity, Film, Gauge, Layers, Timer } from 'lucide-react'
import type { ReactNode } from 'react'
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

function StatusDot({ link }: { link: LinkState }): ReactNode {
  const color =
    link === 'connected' ? 'bg-ok' : link === 'failed' ? 'bg-danger' : 'bg-warn animate-pulse'
  return <span className={cn('inline-block size-2.5 rounded-full', color)} />
}

function Stat({ icon, label, value }: { icon: ReactNode; label: string; value: string }): ReactNode {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="flex items-center gap-2 text-sm text-muted">
        {icon}
        {label}
      </div>
      <div className="mt-2 truncate text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  )
}

export default function App(): ReactNode {
  const { link, error, heartbeat } = useEngine()
  const capture = heartbeat?.capture

  return (
    <main className="mx-auto flex h-full max-w-5xl flex-col gap-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">GameSense</h1>
          <p className="text-sm text-muted">Developer dashboard · Milestone 0</p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-sm">
          <StatusDot link={link} />
          {LINK_LABEL[link]}
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

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          icon={<Timer className="size-4" />}
          label="Uptime"
          value={heartbeat ? formatUptime(heartbeat.uptime_seconds) : '—'}
        />
        <Stat
          icon={<Film className="size-4" />}
          label="Capture"
          value={capture ? (capture.running ? capture.source : 'idle') : '—'}
        />
        <Stat
          icon={<Gauge className="size-4" />}
          label="Sample rate"
          value={capture ? `${capture.fps.toFixed(1)} fps` : '—'}
        />
        <Stat
          icon={<Layers className="size-4" />}
          label="Buffered frames"
          value={capture ? String(capture.buffered_frames) : '—'}
        />
      </section>

      <section className="rounded-xl border border-border bg-surface p-4 text-sm">
        <div className="flex items-center gap-2 text-muted">
          <Activity className="size-4" />
          Capture source
        </div>
        <p className="mt-2 break-all">
          {capture?.target ?? 'No capture source. Run "npm run sample-clip" to create a demo clip.'}
        </p>
        {capture?.frame_width && (
          <p className="mt-1 text-muted">
            Frames {capture.frame_width}×{capture.frame_height} · engine v
            {heartbeat?.engine_version}
          </p>
        )}
      </section>
    </main>
  )
}
