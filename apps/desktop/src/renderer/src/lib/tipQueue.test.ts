import type { CoachingDecision } from '@contracts'
import { describe, expect, it } from 'vitest'
import { advance, dismiss, emptyQueue, enqueue, remainingFraction } from './tipQueue'

function tip(id: string, priority: CoachingDecision['priority'] = 'info', expires = 10): CoachingDecision {
  return {
    id,
    category: 'test',
    action: id,
    message: `Tip ${id}`,
    priority,
    confidence: 0.9,
    delivery: 'immediate',
    expires_in_seconds: expires
  }
}

describe('tip queue', () => {
  it('shows the first tip immediately', () => {
    const s = enqueue(emptyQueue, tip('a'), 0)
    expect(s.active?.decision.id).toBe('a')
    expect(s.active?.expiresAt).toBe(10_000)
  })

  it('higher priority replaces, lower priority waits', () => {
    let s = enqueue(emptyQueue, tip('a', 'important'), 0)
    s = enqueue(s, tip('b', 'info'), 100)
    expect(s.active?.decision.id).toBe('a')
    expect(s.queue.map((t) => t.decision.id)).toEqual(['b'])
    s = enqueue(s, tip('c', 'urgent'), 200)
    expect(s.active?.decision.id).toBe('c')
  })

  it('advances to the next fresh tip on expiry and skips stale ones', () => {
    let s = enqueue(emptyQueue, tip('a', 'info', 5), 0)
    s = enqueue(s, tip('stale', 'info', 3), 0)
    s = enqueue(s, tip('fresh', 'info', 20), 1000)
    s = advance(s, 4000)
    expect(s.active?.decision.id).toBe('a')
    s = advance(s, 5000)
    expect(s.active?.decision.id).toBe('fresh')
    expect(s.queue).toHaveLength(0)
  })

  it('dismiss shows the next tip or clears', () => {
    let s = enqueue(emptyQueue, tip('a'), 0)
    s = enqueue(s, tip('b'), 0)
    s = dismiss(s, 100)
    expect(s.active?.decision.id).toBe('b')
    s = dismiss(s, 200)
    expect(s.active).toBeNull()
  })

  it('caps the queue length', () => {
    let s = enqueue(emptyQueue, tip('a', 'urgent'), 0)
    for (const id of ['b', 'c', 'd', 'e']) s = enqueue(s, tip(id), 0)
    expect(s.queue).toHaveLength(3)
  })

  it('computes the progress bar fraction', () => {
    const s = enqueue(emptyQueue, tip('a', 'info', 10), 0)
    expect(remainingFraction(s.active!, 5000)).toBeCloseTo(0.5)
    expect(remainingFraction(s.active!, 20_000)).toBe(0)
  })
})
