import type { TipEvent } from '@contracts'
import { type ReactNode, useCallback, useEffect, useReducer, useRef } from 'react'
import { TipCard } from './components/TipCard'
import { useEngine } from './hooks/useEngine'
import {
  advance,
  dismiss,
  emptyQueue,
  enqueue,
  remainingFraction,
  type TipQueueState
} from './lib/tipQueue'
import { cn } from './lib/utils'

type Action =
  | { type: 'tip'; event: TipEvent; now: number }
  | { type: 'tick'; now: number }
  | { type: 'dismiss'; now: number }

function reducer(state: TipQueueState, action: Action): TipQueueState {
  switch (action.type) {
    case 'tip':
      return enqueue(state, action.event.decision, action.now)
    case 'tick':
      return advance(state, action.now)
    case 'dismiss':
      return dismiss(state, action.now)
  }
}

/** The in-game overlay: one glanceable tip card plus a small status dot. */
export default function OverlayApp(): ReactNode {
  const [queue, dispatch] = useReducer(reducer, emptyQueue)
  const onTip = useCallback((event: TipEvent) => dispatch({ type: 'tip', event, now: Date.now() }), [])
  const { link, heartbeat, send } = useEngine(onTip)
  const activeRef = useRef(queue.active)
  activeRef.current = queue.active
  const paused = heartbeat?.coaching?.paused ?? false

  useEffect(() => {
    const id = setInterval(() => dispatch({ type: 'tick', now: Date.now() }), 200)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    return window.gamesense.onHotkey((hotkey) => {
      const active = activeRef.current
      if (hotkey === 'pause') {
        send({ type: 'control', action: paused ? 'resume' : 'pause' })
        return
      }
      if (!active) return
      const tipId = active.decision.id
      if (hotkey === 'useful') send({ type: 'feedback', tip_id: tipId, rating: 'useful' })
      if (hotkey === 'not_useful') send({ type: 'feedback', tip_id: tipId, rating: 'not_useful' })
      if (hotkey === 'dismiss') send({ type: 'feedback', tip_id: tipId, rating: 'dismissed' })
      dispatch({ type: 'dismiss', now: Date.now() })
    })
  }, [send, paused])

  const dot =
    link !== 'connected' || heartbeat?.coaching?.live_allowed === false
      ? 'bg-danger'
      : paused
        ? 'bg-muted'
        : 'bg-ok'

  return (
    <div className="pointer-events-none fixed inset-0 select-none">
      <div className="absolute top-6 right-6 flex flex-col items-end gap-2">
        <span
          className={cn('size-2 rounded-full opacity-70', dot)}
          title={paused ? 'Coaching paused' : 'GameSense'}
        />
        {queue.active && (
          <TipCard
            key={queue.active.decision.id}
            decision={queue.active.decision}
            fraction={remainingFraction(queue.active, Date.now())}
          />
        )}
      </div>
    </div>
  )
}
