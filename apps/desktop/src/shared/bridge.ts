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

export interface GameSenseBridge {
  platform: string
  getEngineConnection(): Promise<EngineConnection>
}

export const IPC = {
  engineConnection: 'engine:connection'
} as const
