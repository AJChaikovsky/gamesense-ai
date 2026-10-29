import type { CoachingDecision } from '@contracts'

/**
 * Overlay tip queue (docs/ui-design.md): one tip on screen, higher priority replaces
 * lower, a short queue for the rest, and nothing is shown after it has gone stale.
 * Pure functions so the rules are unit-tested.
 */

const RANK: Record<CoachingDecision['priority'], number> = { info: 0, important: 1, urgent: 2 }
const MIN_SHOW_MS = 1500
const MAX_QUEUE = 3

export interface QueuedTip {
  decision: CoachingDecision
  receivedAt: number
}

export interface ActiveTip extends QueuedTip {
  shownAt: number
  expiresAt: number
}

export interface TipQueueState {
  active: ActiveTip | null
  queue: QueuedTip[]
}

export const emptyQueue: TipQueueState = { active: null, queue: [] }

function deadline(tip: QueuedTip): number {
  return tip.receivedAt + tip.decision.expires_in_seconds * 1000
}

function show(tip: QueuedTip, now: number): ActiveTip | null {
  const expiresAt = deadline(tip)
  return expiresAt - now >= MIN_SHOW_MS ? { ...tip, shownAt: now, expiresAt } : null
}

function next(queue: QueuedTip[], now: number): TipQueueState {
  const fresh = queue
    .filter((t) => deadline(t) - now >= MIN_SHOW_MS)
    .sort((a, b) => RANK[b.decision.priority] - RANK[a.decision.priority] || a.receivedAt - b.receivedAt)
  for (let i = 0; i < fresh.length; i++) {
    const active = show(fresh[i], now)
    if (active) return { active, queue: fresh.slice(i + 1) }
  }
  return emptyQueue
}

export function enqueue(state: TipQueueState, decision: CoachingDecision, now: number): TipQueueState {
  const tip: QueuedTip = { decision, receivedAt: now }
  if (!state.active) {
    const active = show(tip, now)
    return active ? { active, queue: state.queue } : state
  }
  if (RANK[decision.priority] > RANK[state.active.decision.priority]) {
    const active = show(tip, now)
    return active ? { active, queue: state.queue } : state
  }
  const queue = [...state.queue, tip]
    .sort((a, b) => RANK[b.decision.priority] - RANK[a.decision.priority] || b.receivedAt - a.receivedAt)
    .slice(0, MAX_QUEUE)
  return { active: state.active, queue }
}

export function advance(state: TipQueueState, now: number): TipQueueState {
  if (state.active && now < state.active.expiresAt) return state
  return next(state.queue, now)
}

export function dismiss(state: TipQueueState, now: number): TipQueueState {
  return next(state.queue, now)
}

/** 1 when just shown, 0 at expiry. */
export function remainingFraction(tip: ActiveTip, now: number): number {
  const total = tip.expiresAt - tip.shownAt
  return total <= 0 ? 0 : Math.max(0, Math.min(1, (tip.expiresAt - now) / total))
}
