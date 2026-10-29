import { describe, expect, it } from 'vitest'
import { formatUptime, parseEngineEvent, reconnectDelay } from './engineClient'

describe('parseEngineEvent', () => {
  it('accepts known event types', () => {
    const event = parseEngineEvent(JSON.stringify({ type: 'heartbeat', uptime_seconds: 1 }))
    expect(event?.type).toBe('heartbeat')
  })

  it('rejects junk', () => {
    expect(parseEngineEvent('not json')).toBeNull()
    expect(parseEngineEvent(JSON.stringify({ type: 'nope' }))).toBeNull()
    expect(parseEngineEvent(42)).toBeNull()
  })
})

describe('reconnectDelay', () => {
  it('backs off exponentially and caps', () => {
    expect(reconnectDelay(0)).toBe(500)
    expect(reconnectDelay(1)).toBe(1000)
    expect(reconnectDelay(10)).toBe(10_000)
  })
})

describe('formatUptime', () => {
  it('formats seconds, minutes and hours', () => {
    expect(formatUptime(5.4)).toBe('5s')
    expect(formatUptime(65)).toBe('1m 5s')
    expect(formatUptime(3725)).toBe('1h 2m')
  })
})
