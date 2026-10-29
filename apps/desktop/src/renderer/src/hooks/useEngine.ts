import type { HeartbeatEvent, StatusEvent, TipEvent } from '@contracts'
import { useEffect, useState } from 'react'
import { parseEngineEvent, reconnectDelay } from '../lib/engineClient'

export type LinkState = 'starting' | 'connecting' | 'connected' | 'disconnected' | 'failed'

export interface EngineView {
  link: LinkState
  error?: string
  heartbeat?: HeartbeatEvent
  lastTip?: TipEvent
  lastStatus?: StatusEvent
}

/** Connects to the local engine WebSocket and keeps the latest events, reconnecting on drop. */
export function useEngine(): EngineView {
  const [view, setView] = useState<EngineView>({ link: 'starting' })

  useEffect(() => {
    let socket: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let attempt = 0
    let cancelled = false

    const connect = async (): Promise<void> => {
      const conn = await window.gamesense.getEngineConnection()
      if (cancelled) return
      if (conn.status === 'failed') {
        setView({ link: 'failed', error: conn.error })
        return
      }
      if (conn.status !== 'ready') return

      setView((v) => ({ ...v, link: 'connecting' }))
      socket = new WebSocket(`${conn.url}?token=${encodeURIComponent(conn.token)}`)
      socket.onopen = () => {
        attempt = 0
        setView((v) => ({ ...v, link: 'connected', error: undefined }))
      }
      socket.onmessage = (msg) => {
        const event = parseEngineEvent(msg.data)
        if (!event) return
        setView((v) => {
          switch (event.type) {
            case 'heartbeat':
              return { ...v, heartbeat: event }
            case 'tip':
              return { ...v, lastTip: event }
            case 'status':
              return { ...v, lastStatus: event }
            default:
              return v
          }
        })
      }
      socket.onclose = () => {
        if (cancelled) return
        setView((v) => ({ ...v, link: 'disconnected' }))
        timer = setTimeout(() => void connect(), reconnectDelay(attempt++))
      }
    }

    void connect()
    return () => {
      cancelled = true
      clearTimeout(timer)
      socket?.close()
    }
  }, [])

  return view
}
