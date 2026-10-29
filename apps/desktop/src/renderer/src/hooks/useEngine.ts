import type { ClientMessage, HeartbeatEvent, StatusEvent, TipEvent } from '@contracts'
import { useCallback, useEffect, useRef, useState } from 'react'
import { parseEngineEvent, reconnectDelay } from '../lib/engineClient'

export type LinkState = 'starting' | 'connecting' | 'connected' | 'disconnected' | 'failed'

export interface EngineView {
  link: LinkState
  error?: string
  heartbeat?: HeartbeatEvent
  lastStatus?: StatusEvent
  /** Most recent tips, newest first. */
  tips: TipEvent[]
}

export interface UseEngine extends EngineView {
  send(message: ClientMessage): void
}

const MAX_TIPS = 20

/**
 * Connects to the local engine WebSocket, keeps the latest events, reconnects on drop.
 * `onTip` fires once per incoming tip (used by the overlay's queue).
 */
export function useEngine(onTip?: (tip: TipEvent) => void): UseEngine {
  const [view, setView] = useState<EngineView>({ link: 'starting', tips: [] })
  const socketRef = useRef<WebSocket | null>(null)
  const onTipRef = useRef(onTip)
  onTipRef.current = onTip

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    let cancelled = false

    const connect = async (): Promise<void> => {
      const conn = await window.gamesense.getEngineConnection()
      if (cancelled) return
      if (conn.status === 'failed') {
        setView((v) => ({ ...v, link: 'failed', error: conn.error }))
        return
      }
      if (conn.status !== 'ready') return

      setView((v) => ({ ...v, link: 'connecting' }))
      const socket = new WebSocket(`${conn.url}?token=${encodeURIComponent(conn.token)}`)
      socketRef.current = socket
      socket.onopen = () => {
        attempt = 0
        setView((v) => ({ ...v, link: 'connected', error: undefined }))
      }
      socket.onmessage = (msg) => {
        const event = parseEngineEvent(msg.data)
        if (!event) return
        if (event.type === 'tip') onTipRef.current?.(event)
        setView((v) => {
          switch (event.type) {
            case 'heartbeat':
              return { ...v, heartbeat: event }
            case 'tip':
              return { ...v, tips: [event, ...v.tips].slice(0, MAX_TIPS) }
            case 'status':
              return { ...v, lastStatus: event }
            default:
              return v
          }
        })
      }
      socket.onclose = () => {
        if (socketRef.current === socket) socketRef.current = null
        if (cancelled) return
        setView((v) => ({ ...v, link: 'disconnected' }))
        timer = setTimeout(() => void connect(), reconnectDelay(attempt++))
      }
    }

    void connect()
    return () => {
      cancelled = true
      clearTimeout(timer)
      socketRef.current?.close()
    }
  }, [])

  const send = useCallback((message: ClientMessage) => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message))
  }, [])

  return { ...view, send }
}
