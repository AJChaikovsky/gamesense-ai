/**
 * The only surface the renderer may use to reach the desktop shell.
 *
 * Keep this small and shell-agnostic: if we move from Electron to Tauri, only
 * the preload implementation of this interface changes, not the React code.
 */
export type EngineConnection =
  | { status: 'starting' }
  | { status: 'ready'; url: string; token: string }
  | { status: 'failed'; error: string }

export type Hotkey = 'dismiss' | 'useful' | 'not_useful' | 'pause'

export interface AppMetrics {
  /** Memory of all app processes (main, renderers, GPU), in MB: private bytes on Windows, working set elsewhere. */
  memoryMb: number
  /** Total CPU use across app processes, percent of one core. */
  cpuPercent: number
  processCount: number
}

export interface GameSenseBridge {
  platform: string
  getEngineConnection(): Promise<EngineConnection>
  getAppMetrics(): Promise<AppMetrics>
  setOverlayVisible(visible: boolean): Promise<void>
  /** Subscribe to global hotkeys; returns an unsubscribe function. */
  onHotkey(listener: (hotkey: Hotkey) => void): () => void
  hotkeyLabels: Record<Hotkey, string>
}

export const IPC = {
  engineConnection: 'engine:connection',
  appMetrics: 'app:metrics',
  overlayVisible: 'overlay:visible',
  hotkey: 'hotkey'
} as const

/** Default global shortcuts (Electron accelerator syntax). Rebinding arrives in M7. */
export const DEFAULT_HOTKEYS: Record<Hotkey, string> = {
  dismiss: 'Alt+Shift+X',
  useful: 'Alt+Shift+Up',
  not_useful: 'Alt+Shift+Down',
  pause: 'Alt+Shift+P'
}
