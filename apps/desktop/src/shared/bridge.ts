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

export interface HotkeyStatus {
  accelerator: string
  registered: boolean
}

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
  /** Each hotkey's shortcut and whether the OS accepted it (false = another app holds it). */
  getHotkeyStatus(): Promise<Record<Hotkey, HotkeyStatus>>
}

export const IPC = {
  engineConnection: 'engine:connection',
  appMetrics: 'app:metrics',
  overlayVisible: 'overlay:visible',
  hotkey: 'hotkey',
  hotkeyStatus: 'hotkey:status'
} as const

/**
 * Default global shortcuts (Electron accelerator syntax). Until the settings screen
 * lands in M7, override one with GAMESENSE_HOTKEY_<NAME>, e.g. GAMESENSE_HOTKEY_DISMISS=Ctrl+Shift+X.
 */
export const DEFAULT_HOTKEYS: Record<Hotkey, string> = {
  dismiss: 'Alt+Shift+X',
  useful: 'Alt+Shift+Up',
  not_useful: 'Alt+Shift+Down',
  pause: 'Alt+Shift+P'
}
