import type { CoachingDecision } from '@contracts'
import {
  Coins,
  Crosshair,
  HeartPulse,
  Lightbulb,
  type LucideIcon,
  MapPin,
  Shield,
  Swords,
  Zap
} from 'lucide-react'
import { type ReactNode, useEffect, useRef } from 'react'
import { cn } from '../lib/utils'

const EDGE: Record<CoachingDecision['priority'], string> = {
  info: 'border-l-muted',
  important: 'border-l-warn',
  urgent: 'border-l-danger'
}

const BAR: Record<CoachingDecision['priority'], string> = {
  info: 'bg-muted',
  important: 'bg-warn',
  urgent: 'bg-danger'
}

function iconFor(category: string): LucideIcon {
  const c = category.toLowerCase()
  if (/(surviv|health|heal)/.test(c)) return HeartPulse
  if (/(econom|money|resource|inventory)/.test(c)) return Coins
  if (/(aim|crosshair)/.test(c)) return Crosshair
  if (/(position|map|night)/.test(c)) return MapPin
  if (/(defen|shield|safety)/.test(c)) return Shield
  if (/(combat|pattern|boss|fight)/.test(c)) return Swords
  if (/(stamina|energy|utility)/.test(c)) return Zap
  return Lightbulb
}

/**
 * The countdown bar runs as one compositor animation (scaleX) from the remaining
 * fraction to zero, so it moves smoothly instead of stepping on each React tick.
 * It restarts only when the tip's timing changes.
 */
function useCountdown(shownAt: number, expiresAt: number) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const now = Date.now()
    const total = expiresAt - shownAt
    const remaining = Math.max(0, expiresAt - now)
    const from = total > 0 ? Math.min(1, remaining / total) : 0
    const animation = el.animate([{ transform: `scaleX(${from})` }, { transform: 'scaleX(0)' }], {
      duration: remaining,
      easing: 'linear',
      fill: 'forwards'
    })
    return () => animation.cancel()
  }, [shownAt, expiresAt])
  return ref
}

export function TipCard({
  decision,
  shownAt,
  expiresAt,
  className
}: {
  decision: CoachingDecision
  shownAt: number
  expiresAt: number
  className?: string
}): ReactNode {
  const Icon = iconFor(decision.category)
  const bar = useCountdown(shownAt, expiresAt)
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'w-[340px] overflow-hidden rounded-xl border border-white/10 border-l-4 bg-[#0b0d12]/85 text-text shadow-2xl backdrop-blur-sm',
        'animate-[tip-in_160ms_ease-out] motion-reduce:animate-none',
        EDGE[decision.priority],
        className
      )}
    >
      <div className="flex items-start gap-3 px-4 pt-3 pb-2.5">
        <Icon className="mt-0.5 size-5 shrink-0 text-text/80" aria-hidden />
        <div className="min-w-0">
          <p className="text-[17px] leading-snug font-semibold">{decision.message}</p>
          {decision.detail && <p className="mt-0.5 text-sm leading-snug text-muted">{decision.detail}</p>}
        </div>
      </div>
      <div className="h-1 bg-white/5">
        <div
          ref={bar}
          className={cn('h-full origin-left will-change-transform', BAR[decision.priority])}
        />
      </div>
    </div>
  )
}
