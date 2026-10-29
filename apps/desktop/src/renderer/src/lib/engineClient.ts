import type { EngineEvent } from '@contracts'

const EVENT_TYPES = new Set(['heartbeat', 'tip', 'status'])

/** Parse one WebSocket message from the engine; returns null for anything unexpected. */
export function parseEngineEvent(raw: unknown): EngineEvent | null {
  if (typeof raw !== 'string') return null
  try {
    const data = JSON.parse(raw) as { type?: unknown }
    return typeof data.type === 'string' && EVENT_TYPES.has(data.type)
      ? (data as EngineEvent)
      : null
  } catch {
    return null
  }
}

/** Exponential reconnect backoff: 0.5 s, 1 s, 2 s ... capped at 10 s. */
export function reconnectDelay(attempt: number): number {
  return Math.min(10_000, 500 * 2 ** Math.max(0, attempt))
}

export function formatUptime(seconds: number): string {
  const s = Math.floor(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${sec}s` : `${sec}s`
}
